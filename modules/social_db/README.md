# Social DB

SentryBOT'un birleşik sosyal hafıza katmanıdır. Kişi, yüz, sohbet, ilişki, mood ve etkileşim verilerini tek SQLite dosyasında toplar. HTTP servisi yoktur; kütüphane modülüdür.

## Sorumluluklar

- Kişi kimliği ve yüz vektörleri
- Görülme günlüğü, sohbet geçmişi, ilişki tercihleri
- Mood snapshot, ritüel takibi, etkileşim olayları
- Sahip oturum pencereleri
- Eski JSON depolarının yerini alan tek doğruluk kaynağı

## Mimari

- Aggregator: `db.py` (`SocialDB`)
- Şema: `schema.py` (lazy migrate)
- Repository'ler: `repositories/` (10 repo)
- Singleton: `get_default()` / `set_default()`

Gateway `_include_social_db` varsayılan olarak (`include.social_db: true`) startup'ta `SocialDB` oluşturur ve `set_default()` ile kaydeder.

## Repository Yapısı

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

## Kullanım

```python
from modules.social_db import get_default

db = get_default()
if db is not None:
    person = db.persons.upsert(name="Emir", trust_score=0.6)
```

Testlerde izole instance:
```python
from modules.social_db.db import SocialDB
db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
```

## Konfigürasyon

`config/config.yml`:
- `path` — SQLite dosya yolu
- `wal`, `cache_size_kb`, `busy_timeout_ms`
- `default_owner_name`, `auto_migrate`

## İlişkiler

- `vlm_bridge`: yüz/kişi hafızası (`face_manager`, `person_identity`, `people_memory`)
- `autonomy`: mood, rituals, relationship memory, interaction feedback
- `agent_core`: tool'lar ve sosyal bağlam
- `interactions`: olay sayaçları
- `config_center`: runtime registry snapshot

Otonomlukta uzun süreli sosyal bağlam ve kişiselleştirmenin kalıcı hafıza katmanıdır.

Geçiş: `tools/social_db_migrate.py`
