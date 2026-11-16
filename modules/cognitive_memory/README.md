# Cognitive Memory — Bilişsel ve Sosyal Bellek Motoru

`modules.cognitive_memory`, SentryBOT'un insanları tanımasını, önceki sohbetleri hatırlamasını, yüz embedding vektörlerini saklamasını ve robot-insan ilişkilerini zaman içinde geliştirmesini sağlayan kalıcı bellek motorudur.

Mimari detaylar, SQLite WAL şeması ve Mermaid/Graphviz veri akış diyagramları için:
- 📖 [architecture_cognitive_memory.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/cognitive_memory/architecture_cognitive_memory.md)
- 📊 [architecture_cognitive_memory.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/cognitive_memory/architecture_cognitive_memory.dot) (Graphviz DOT kaynağı)
- 🖼️ [architecture_cognitive_memory.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/cognitive_memory/architecture_cognitive_memory.svg)

---

## 🚀 Temel Yetenekler

1. **İlişkisel Sosyal Veritabanı (`SocialDB`):** SQLite WAL modunda çalışan, `11` tablolu, `_tx_depth` ile iç içe transaction destekli ve thread-safe veritabanı motoru.
2. **Kişi ve Yüz Tanıma (`PersonsRepo`, `FaceDescriptorsRepo`):** Yüz embedding tanımlayıcıları ve atomik `adjust_trust()` güven skoru yönetimi.
3. **İlişki ve Yakınlık Takibi (`RelationshipsRepo`, `RelationshipMemory`):** Tek transaction içinde gruplanmış `add_chat()`, salt-okunur `social_profile()` ve paylaşımlı üstel `decay_salience` azalması.
4. **Uzun Dönem Sohbet & Dünya Belleği (`ChatRAG`, `WorldMemoryRAG`, `WorldMemory`):** SQL'e indirilmiş `person_id`/`kinds` FTS5 + birim-normlu semantik rerank, `expiry`/`supersedes` doğrulaması, boş-başlangıç FTS koruması ve arka plan `backfill_embeddings()` / `.backup()`.
5. **Uyku Konsolidasyonu (`SleepConsolidator`):** Şarj/boşta kalma anlarında `SocialDB.moments.decay()`, `ChatRAG.remember_day_summary()`, `backfill_embeddings()` ve çevrimiçi `sqlite3.Connection.backup()` yedekleme yürütümü.

---

## 🛠️ Hızlı Kullanım Örnekleri

### 1. Veritabanına Bağlanma ve Kişi Bilgisi Çekme
```python
from modules.cognitive_memory import SocialDB
from modules.cognitive_memory.services.relationship_memory import RelationshipMemory
from modules.cognitive_memory.services.world_memory_rag import WorldMemoryRAG

db = SocialDB()
person = db.persons.get_by_name("Emir")
rel_mem = RelationshipMemory(social_db=db)
rel_mem.add_chat("Emir", "user", "Bugün nasılsın Sentry?")

rag = WorldMemoryRAG({"db_path": "data/world_memory.sqlite3"})
recalled = rag.recall(query="En sevilen içecek", limit=2)
```

---

## 🗄️ Veritabanı Tabloları (`11` Repo Tablosu + `schema_version`)
- `persons`, `face_descriptors`, `sightings`, `chat_episodes`, `relationships`, `moments`, `mood_snapshots`, `rituals`, `interaction_events`, `owner_sessions`, `world_memories`, `world_observations`

---

## 🧪 Testlerin Çalıştırılması

```bash
pytest tests/modules/cognitive_memory -v
```