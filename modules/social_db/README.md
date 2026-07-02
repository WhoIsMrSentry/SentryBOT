# Social DB

`vlm_bridge`, `autonomy`, `agent_core`, `interactions` ve `config_center` tarafından paylaşılan, kişi/ilişki/sohbet/mood verilerini tek bir SQLite dosyasında toplayan birleşik sosyal hafıza katmanı.

## Ne İşe Yarar?
- Kişileri (`persons`), yüz tanıma vektörlerini (`face_descriptors`), görülme kayıtlarını (`sightings`) tek şema altında saklar.
- Sohbet geçmişini (`chat_episodes`), tercihleri (`relationships`) ve öne çıkan anıları (`moments`) kişi bazlı tutar.
- Mood anlık görüntülerini (`mood_snapshots`), günlük ritüelleri (`rituals`) ve etkileşim olaylarını (`interaction_events`) loglar.
- Sahip oturumlarını (`owner_sessions`) izler.
- Eski JSON tabanlı depoların (`person_identity.json`, `faces.json`, `people_memory.json`, `relationship_memory.json`) yerini alan tek doğruluk kaynağıdır; `tools/social_db_migrate.py` ile geçiş yapılabilir.

## Bağımsız Kullanım
`social_db`'nin kendi HTTP servisi/API yüzeyi yoktur; saf bir kütüphane modülüdür. Diğer modüller `get_default()` ile paylaşılan, süreç geneli tekil örneği alır:

```python
from modules.social_db import get_default, set_default
from modules.social_db.db import SocialDB
from modules.social_db.config_loader import load_config

cfg = load_config(None)
db = SocialDB(path=cfg["path"], wal=cfg.get("wal", True))
set_default(db)

...

db = get_default()
if db is not None:
    person = db.persons.upsert(name="Emir", trust_score=0.6)
```

Testlerde izole, kalıcı olmayan bir örnek oluşturmak için geçici bir dosya kullanılır:

```python
db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
try:
    ...
finally:
    db.close()
```

## Repository Yapısı (`repositories/`)
| Repo | Tablo | Sorumluluk |
|------|-------|------------|
| `PersonsRepo` | `persons` | Kişi CRUD, sahip işaretleme, güven skoru ayarı |
| `FaceDescriptorsRepo` | `face_descriptors` | ORB / face_recognition vektör blob'ları |
| `SightingsRepo` | `sightings` | Görülme (append-only) günlüğü |
| `ChatEpisodesRepo` | `chat_episodes` | Sohbet geçmişi + budama (`prune_for_person`) |
| `RelationshipsRepo` | `relationships` | Anahtar/değer tercihler (likes, dislikes, ...) |
| `MomentsRepo` | `moments` | Salience ağırlıklı anı metinleri + decay |
| `MoodSnapshotsRepo` | `mood_snapshots` | Periyodik mood anlık görüntüleri |
| `RitualsRepo` | `rituals` | Günlük ritüel takibi (idempotent) |
| `InteractionEventsRepo` | `interaction_events` | Etkileşim/olay sayaç günlüğü |
| `OwnerSessionsRepo` | `owner_sessions` | Sahip oturum pencereleri |

Her repository yalnızca `SocialDB`'nin paylaşılan bağlantısına bir geri referans tutar; kendi state'i yoktur.

## Config Anahtarları (`config/config.yml`)
- `path` — SQLite dosya yolu (proje köküne göre veya mutlak)
- `wal` — WAL journal modu (varsayılan `true`)
- `cache_size_kb` — SQLite `PRAGMA cache_size` ayarı
- `busy_timeout_ms` — kilit bekleme süresi (ms)
- `default_owner_name` — ilk kurulumda sahip olarak işaretlenecek isim (boşsa atlanır)
- `auto_migrate` — açılışta şemayı otomatik oluştur/güncelle (varsayılan `true`)
