# Cognitive Memory — Bilişsel ve Sosyal Bellek Motoru

`modules.cognitive_memory`, SentryBOT'un insanları tanımasını, önceki sohbetleri hatırlamasını, yüz embedding vektörlerini saklamasını ve robot-insan ilişkilerini zaman içinde geliştirmesini sağlayan kalıcı bellek motorudur.

Mimari detaylar, SQLite WAL şeması ve Mermaid/Graphviz veri akış diyagramları için:
- 📖 [architecture_cognitive_memory.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/cognitive_memory/architecture_cognitive_memory.md)
- 📊 [architecture_cognitive_memory.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/cognitive_memory/architecture_cognitive_memory.dot) (Graphviz DOT kaynağı)
- 🖼️ [architecture_cognitive_memory.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/cognitive_memory/architecture_cognitive_memory.svg)

---

## 🚀 Temel Yetenekler

1. **İlişkisel Sosyal Veritabanı (`SocialDB`):** SQLite WAL modunda çalışan, 10 tablolu, bağlantı havuzlu ve thread-safe veritabanı motoru.
2. **Kişi ve Yüz Tanıma (`PersonRepository`, `FaceDescriptorRepository`):** 512 boyutlu yüz embedding vektörleri ile kimlik eşleştirme.
3. **İlişki ve Yakınlık Takibi (`RelationshipRepository`):** Güven seviyesi, tanışıklık skoru ve etkileşim sıklığı analizi.
4. **Epizodik Sohbet Kaydı (`ChatEpisodeRepository`):** Geçmiş konuşmaların bağlamsal saklanması.
5. **Hibrit RAG Bilgi Arama (`WorldMemoryRAG`):** BM25 anahtar kelime ve vektör benzerliği ile robotun çevresi hakkındaki olguları LLM istemine getirme.
6. **Uyku Konsolidasyonu (`SleepConsolidator`):** Gece veya şarj anında hatıraların özetlenmesi ve optimize edilmesi.

---

## 🛠️ Hızlı Kullanım Örnekleri

### 1. Veritabanına Bağlanma ve Kişi Bilgisi Çekme
```python
from modules.cognitive_memory.db import get_social_db
from modules.cognitive_memory.repositories.persons import PersonRepository

db = get_social_db()
person_repo = PersonRepository(db)

# Kişiyi kimliğe veya takma isme göre bulma
person = person_repo.get_by_name("Emo")
if person:
    print(f"Tanınan Kişi: {person['name']} (Rol: {person['role']}, Güven: {person['trust_level']})")
```

### 2. Diyalog Kaydetme ve İlişki Güncelleme
```python
from modules.cognitive_memory.services.relationship_memory import RelationshipMemory

rel_mem = RelationshipMemory(db)
rel_mem.ingest_dialogue_turn(
    person_id=person["id"],
    user_text="Bugün nasılsın Sentry?",
    robot_text="Çok iyiyim, seni görmek güzel!",
    sentiment=0.8,
)
```

### 3. Hibrit RAG ile Olgu Sorgulama
```python
from modules.cognitive_memory.services.world_memory_rag import WorldMemoryRAG

rag = WorldMemoryRAG(db)
facts = rag.search(query="En sevilen içecek", limit=2)
for fact in facts:
    print(f"- {fact['subject']} {fact['predicate']} {fact['object']}")
```

---

## 🗄️ Veritabanı Tabloları (10 Tablo)
- `persons`: Kişi profilleri ve roller
- `face_descriptors`: 512-dim yüz embedding vektörleri
- `sightings`: Kameranın kişiyi görüş kayıtları
- `interaction_events`: Etkileşim günlüğü (dokunma, ses, komut)
- `relationships`: Robot ile kişi arasındaki samimiyet puanı
- `rituals`: Tekrarlayan rutinler ve alışkanlıklar
- `moments`: Önemli ve unutulmaz anılar
- `chat_episodes`: Sohbet cümleleri ve niyetler
- `mood_snapshots`: Duygu durumu geçmişi
- `world_memory`: Dünya ve ortam olguları

---

## 🧪 Testlerin Çalıştırılması

```bash
pytest tests/modules/cognitive_memory -v
```