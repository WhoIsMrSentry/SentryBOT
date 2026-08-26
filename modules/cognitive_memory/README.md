# Cognitive Memory (eski Social DB)

SentryBOT'un birleşik bilişsel/sosyal hafıza katmanıdır. Kişi, yüz, sohbet, ilişki, mood, ritüel, etkileşim ve dünya gözlem verilerini tek SQLite dosyasında toplar. HTTP servisi yoktur; kütüphane modülüdür.

## Sorumluluklar

- Kişi kimliği ve yüz vektörleri (face descriptors)
- Görülme günlüğü, sohbet geçmişi, ilişki tercihleri
- Mood snapshot, ritüel takibi, etkileşim olayları
- Sahip oturum pencereleri
- **World Memory** - Epizodik olgular, semantik varlıklar, dünya hafızası (RAG)
- Eski JSON depolarının yerini alan tek doğruluk kaynağı

## Mimari (Güncel: 2026-08-20)

- **Core DB**: `db.py` → `SocialDB` (connection, migration, transaction management, WAL)
- **Şema**: `schema.py` (DDL, lazy migrate, version tracking)
- **Repository'ler**: `repositories/` (11 repo - `WorldMemoryRepo` eklendi):
  | Repo | Tablo | Sorumluluk |
  |---|---|---|
  | `PersonsRepo` | `persons` | Kişi CRUD, sahip işaretleme, güven skoru |
  | `FaceDescriptorsRepo` | `face_descriptors` | ORB / face vektör blob'ları |
  | `SightingsRepo` | `sightings` | Görülme günlüğü (append-only) |
  | `ChatEpisodesRepo` | `chat_episodes` | Sohbet geçmişi + budama |
  | `RelationshipsRepo` | `relationships` | Tercih anahtar/değer çiftleri |
  | `MomentsRepo` | `moments` | Salience ağırlıklı anılar |
  | `MoodSnapshotsRepo` | `mood_snapshots` | Periyodik mood kayıtları |
  | `RitualsRepo` | `rituals` | Günlük ritüel takibi |
  | `InteractionEventsRepo` | `interaction_events` | Etkileşim/olay sayaçları |
  | `OwnerSessionsRepo` | `owner_sessions` | Sahip oturum pencereleri |
  | `WorldMemoryRepo` | `world_memories`, `world_observations` | Epizodik olgular, semantik varlıklar, dünya hafızası |
- **Services Katmanı**: `services/`:
  - `world_memory_rag.py` → RAG tabanlı geri çağırma
  - `world_memory_autowriter.py` → Otomatik gözlem yazıcı
  - `preference_learner.py` → İlişki tercihlerinden öğrenme
  - `people_memory.py` → Kişi hafıza yardımcıları
- **Singleton**: `get_default()` / `set_default()` (gateway bootstrap'ta set edilir)

Gateway `_include_social_db` (bootstrap_ops.py) varsayılan olarak (`include.social_db: true`) startup'ta `SocialDB` oluşturur ve `set_default()` ile kaydeder.

## Kullanım

```python
from modules.cognitive_memory import get_default

db = get_default()
if db is not None:
    person = db.persons.upsert(name="Emir", trust_score=0.6)
    # World memory observation
    db.world_memory.record_observation(kind="person", summary="Emir odaya girdi", source="vision")
```

Testlerde izole instance:
```python
from modules.cognitive_memory.db import SocialDB
db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
```

## Konfigürasyon

`modules/cognitive_memory/config/config.yml` + merkezi `config/agent.yaml` (cognitive_memory section):

- `path` — SQLite dosya yolu (default: `data/social.sqlite3`)
- `wal`, `cache_size_kb`, `busy_timeout_ms` (default: WAL on, 4MB cache, 5000ms timeout)
- `default_owner_name`, `auto_migrate`
- `world_memory.enabled`, `persistence.*` (world memory ayarları)

## İlişkiler (Güncel Modül Yolları)

- `vlm_bridge/services/processor_identity.py` → Yüz/kişi hafızası (face register, recognize, remember)
- `autonomy` → Mood, rituals, relationship memory, interaction feedback, world_memory
- `agent_core/services/tools/social_tools.py` → Tool'lar ve sosyal bağlam (person upsert, chat, preferences)
- `expression/interactions` → Olay sayaçları (interaction_events)
- `system_control/config_center` → Runtime registry snapshot

## Otonomlukta Rol

Uzun süreli sosyal bağlam ve kişiselleştirmenin kalıcı hafıza katmanıdır. `autonomy` her döngüde `WorldMemoryRepo` ile gözlem yazır, `RelationshipsRepo` ile tercih öğrenir, `MomentsRepo` ile anı oluşturur.

## Migration

Eski JSON depolarından geçiş: `scripts/migrations/social_db_migrate.py` (idempotent, tüm kaynakları migrate eder)

## Bilinen Sorunlar (Güncel 2026-08-21, Tam Tarama)

1. **SocialDB 183 satır (7242 değil)** - Gerçek `db.py:31 183 satır`, `KB→satır` hatası düzeltildi. Facade uygun boyutta, ek parçalama gerekmez. ✅
2. **Transaction Isolation Kısmen** - `db.py:118 BEGIN IMMEDIATE` + `RLock:44` var, `busy_timeout 5000` + `WAL` + `fetchone:138` cursor close ✅. Ancak `execute:130` ve `fetchone:138` ayrı lock, `common/persistence.py` henüz adopt edilmedi → write queue eklenmeli 🔜
3. **WorldMemoryRepo İki Tablo** - `world_memories` + `world_observations` join için `schema.py` index eksik, `snapshot_stats:154` 8x `COUNT(*)` N+1 -> tek UNION ALL optimizasyonu.
4. **Face Descriptor Blob** - Binary blob, `hotspots ChatEpisodesRepo.append 175` yanında `face_descriptors` similarity Python'da, `common/persistence` vec/FAISS değil.