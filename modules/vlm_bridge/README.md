# VLM Bridge — Çok Modlu Görsel Dil Modeli Köprüsü

`modules.vlm_bridge`, kameradan gelen optik kareleri anlamsal sahne açıklamalarına, nesne tespitlerine, insan duygularına ve uzamsal ilişkilere dönüştüren çok modlu (multimodal) algı köprüsüdür.

Mimari detaylar, sınıf yapıları ve veri akış diyagramları için:
- 📖 [architecture_vlm_bridge.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/vlm_bridge/architecture_vlm_bridge.md)
- 📊 [architecture_vlm_bridge.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/vlm_bridge/architecture_vlm_bridge.dot) (Graphviz DOT kaynağı)
- 🖼️ [architecture_vlm_bridge.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/vlm_bridge/architecture_vlm_bridge.svg)

---

## 🚀 Temel Yetenekler

1. **Hibrit Çok Modlu Çıkarım:** Hem yerel Ollama (`qwen2.5-vl`, `llama3.2-vision`) hem de bulut Google AI Studio (`gemini-2.5-flash`) desteği.
2. **Çıkarım Bütçe Yöneticisi (`InferenceBudgetManager`):** Token tüketimini, kare hızını ve API maliyetlerini koruyan hız sınırlayıcı (rate limiter).
3. **Görsel Bağlam Önbelleği (`VisualContext`):** Ajanın anlık kararlar alabilmesi için son sahne açıklamasını ve nesneleri RAM'de hazır tutar.
4. **Yüz ve Duygu Algılama (`FaceEmotionClassifier`):** İnsan yüzlerini ve yüzdeki duygusal ifadeleri algılayarak robotun anlık tepki vermesini sağlar.
5. **Kafa Yönlendirme:** İnsan yüzüne veya hareketli nesnelere odaklanmak için pan/tilt açı farkları üretir.

---

## 🛠️ Hızlı Kullanım Örnekleri

### 1. En Güncel Sahne Açıklamasını Çekme (Python)
```python
import httpx

resp = httpx.get("http://127.0.0.1:8080/vlm/context/latest")
context = resp.json()
print("Son Sahne Özeti:", context.get("scene"))
print("Görülen Nesneler:", context.get("objects"))
```

### 2. Anlık Sahne Açıklaması Tetikleme (cURL)
```bash
curl -X POST http://127.0.0.1:8080/vlm/describe
```

---

## 📡 REST API Endpointleri

| Metot | Endpoint | Açıklama |
|---|---|---|
| `GET` | `/vlm/healthz` | VLM köprüsü ve model bağlantı durumu |
| `GET` | `/vlm/context/latest` | En son çıkarılan sahne bağlamı ve nesneler |
| `GET` | `/vlm/results/latest` | Ham model yanıtı ve ayrıntılı çıkarım çıktısı |
| `POST` | `/vlm/describe` | Anlık kare yakalayıp sahneyi VLM'e tarif ettirir |
| `POST` | `/vlm/target/follow` | Kafa takibini belirli bir hedefe odaklar |

---

## 🧪 Testlerin Çalıştırılması

```bash
pytest tests/modules/vlm_bridge -v
```