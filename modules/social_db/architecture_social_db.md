# Social DB Modülü Mimarisi

Social DB modülü (`modules/social_db`), robotun kişi tanıma, ilişki hafızası, sohbet geçmişi ve mood/etkileşim telemetrisini tek bir SQLite dosyasında (WAL modlu, thread-safe) birleştiren veri katmanıdır. HTTP yüzeyi yoktur; `vlm_bridge`, `autonomy`, `agent_core`, `config_center` ve `admin_ui` tarafından kütüphane olarak içe aktarılır.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    INIT("SocialDB path ile baslatilir") --> CONN("sqlite3.connect<br>check_same_thread=False")
    CONN --> WAL_CHK{"wal parametresi<br>True mu?"}
    WAL_CHK -- "Evet" --> SET_WAL("PRAGMA journal_mode=WAL")
    WAL_CHK -- "Hayir" --> AUTO_CHK
    SET_WAL --> AUTO_CHK{"auto_migrate<br>True mu?"}

    AUTO_CHK -- "Evet" --> MIGRATE("migrate calisir:<br>CREATE TABLE IF NOT EXISTS + schema_version kaydi")
    AUTO_CHK -- "Hayir" --> ATTACH_REPOS
    MIGRATE --> ATTACH_REPOS("10 repository ornegi<br>olusturulup self'e baglanir")

    ATTACH_REPOS --> READY("db.persons / db.moments / ...<br>kullanima hazir")
    READY --> CLOSE("db.close ile<br>baglanti kapatilir")
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    SocialDB ||--o{ PersonsRepo : owns
    SocialDB ||--o{ FaceDescriptorsRepo : owns
    SocialDB ||--o{ SightingsRepo : owns
    SocialDB ||--o{ ChatEpisodesRepo : owns
    SocialDB ||--o{ RelationshipsRepo : owns
    SocialDB ||--o{ MomentsRepo : owns
    SocialDB ||--o{ MoodSnapshotsRepo : owns
    SocialDB ||--o{ RitualsRepo : owns
    SocialDB ||--o{ InteractionEventsRepo : owns
    SocialDB ||--o{ OwnerSessionsRepo : owns

    PersonsRepo ||--o{ FaceDescriptorsRepo : person_id
    PersonsRepo ||--o{ SightingsRepo : person_id
    PersonsRepo ||--o{ ChatEpisodesRepo : person_id
    PersonsRepo ||--o{ MomentsRepo : person_id

    VlmBridge ||--o{ SocialDB : get_default
    Autonomy ||--o{ SocialDB : get_default
    AgentCore ||--o{ SocialDB : get_default
    AdminUI ||--o{ SocialDB : people_snapshot
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Tek Paylaşımlı Bağlantı + Kilit**
   - `SocialDB`, `check_same_thread=False` ile açılan tek bir `sqlite3.connect` bağlantısını `threading.RLock` arkasında paylaşır. **`if`** birden fazla thread aynı anda yazmaya çalışırsa, `execute`/`transaction` çağrıları kilidi sırayla alır; SQLite seviyesinde `BEGIN IMMEDIATE` ile yazma çakışmaları engellenir.
2. **Canonical İsim ile Tekilleştirme**
   - `PersonsRepo.upsert`, ismi `_canon()` ile (strip + lowercase) normalize eder. **`if`** aynı `canonical_name` zaten varsa mevcut kayıt güncellenir (seen_count artırılabilir); **değilse** yeni `person_id` (`uuid4` kısaltması) ile satır eklenir — aynı kişi için birden fazla kayıt oluşmaz.
3. **Idempotent Migrasyon**
   - `_migrate()` tüm DDL'i `CREATE TABLE IF NOT EXISTS` ile çalıştırır ve `schema_version` tablosuna `INSERT OR IGNORE` yapar. **`if`** modül tekrar tekrar başlatılırsa (örn. testte veya servis restart'ında) migrasyon zararsızca tekrarlanabilir ve mevcut veriye dokunmaz.
4. **Süreç Geneli Varsayılan Örnek**
   - `get_default()` / `set_default()`, modüller arası tekil `SocialDB` paylaşımını sağlar. **`if`** hiçbir modül henüz `set_default()` çağırmadıysa, `get_default()` `None` döner ve çağıran taraflar (örn. `agent_core.tools.search_social_memory`) bunu zarifçe "Social memory unavailable." mesajına çevirir; bir alt sistemin sosyal hafızayı kullanamaması sistemin geri kalanını engellemez.
