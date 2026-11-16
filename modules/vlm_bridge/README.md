# VLM Bridge — Çok Modlu Görsel Dil Modeli Köprüsü

`modules.vlm_bridge`, kameradan gelen optik kareleri anlamsal sahne açıklamalarına, nesne tespitlerine, insan duygularına ve uzamsal ilişkilere dönüştüren çok modlu (multimodal) algı köprüsüdür.

Mimari detaylar, sınıf yapıları ve veri akış diyagramları için:
- 📖 [architecture_vlm_bridge.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/vlm_bridge/architecture_vlm_bridge.md)
- 📊 [architecture_vlm_bridge.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/vlm_bridge/architecture_vlm_bridge.dot) (Graphviz DOT kaynağı)
- 🖼️ [architecture_vlm_bridge.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/vlm_bridge/architecture_vlm_bridge.svg)

---

## 🚀 Temel Yetenekler

1. **Hibrit Çok Modlu Çıkarım:** Yerel Ollama (`qwen3.5:9b`, `single_model_mode: false` ile özelleştirilebilir), bulut Google AI Studio (`gemini`) ve uzak GPU sunucusu (`remote_multimodal_server` — cheap/semantic ayrımı) desteği.
2. **Görsel Örnekleme ve Bütçe Kapısı (`VisionSampler`, `VisionRequestGate`):** Hareket/sahne değişikliği debouncing'i ve thread-safe `vision_semantic_budget` ile gereksiz VLM çağrılarını önler.
3. **Kilitli Yüz Tanıma ve Kimlik Hafızası (`YuNetDetector`, `FaceManager`, `PersonIdentityManager`):** RLock korumalı yüz tespiti/eşleme (kırpılmış ROI'de tek tarama), yüz duygu kestirimi ve atomik JSON / `SocialDB` kişi kaydı.
4. **PD Takip & Kafa Yönlendirme Hakemi (`HeadControlArbiter`, `ProcessorFollowMixin`):** Kilit dışında çalışan non-blocking pan/tilt komutu, otomatik öncelik kilidi koruması, PD yumuşatma ve hedef kaybında yönlü tarama (sweep).
5. **Asenkron Yan Etki & Talep Odaklı MJPEG:** TTS/Ollama/action ağ çağrıları ayrı `_side_effect_queue` işçisinde çalışır; `/vlm/video_feed` yalnız aktif izleyici varken JPEG kodlar.

---

## 🛠️ Hızlı Kullanım Örnekleri

### 1. En Güncel Sahne Açıklamasını Çekme (Python)
```python
import httpx

resp = httpx.get("http://127.0.0.1:8080/vlm/context/latest")
context = (resp.json() or {}).get("context") or {}
print("Son Sahne Özeti:", context.get("scene"))
print("Görülen Nesneler:", context.get("objects"))
```

### 2. Anlık Sahne Sorusu Tetikleme (cURL)
```bash
curl -X POST http://127.0.0.1:8080/vlm/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Önümde ne görüyorsun?"}'
```

---

## 📡 REST API Endpointleri

| Metot | Endpoint | Açıklama |
|---|---|---|
| `GET` | `/vlm/context/latest` | En son çıkarılan sahne bağlamı ve nesneler |
| `POST` | `/vlm/context/refresh` | Güncel karede VLM sahne özetini yeniler |
| `GET` | `/vlm/results/latest` | Son tespit edilen nesne/kişi sonuçları |
| `POST` | `/vlm/results` | Uzak algılama sonuçlarını alır (`X-Auth-Token` fail-closed + Pydantic şema doğrulama) |
| `POST` | `/vlm/ask` | Güncel kare hakkında doğrudan VLM sorusu yanıtlar |
| `POST` | `/vlm/analyze` | Tek kare yerel yüz/nesne/duygu analizi yapar |
| `POST` | `/vlm/ocr` | Uzak sunucu üzerinden metin okuma (OCR) çalıştırır |
| `POST` | `/vlm/follow/start` | Yüz/kişi takibini (ve `owner` takibini) başlatır |
| `POST` | `/vlm/follow/stop` | Kafa takibini durdurur |
| `GET` | `/vlm/follow/status` | Takip ve PD/sweep durumunu döner |
| `GET` / `POST` | `/vlm/head/status`, `/vlm/head/move` | `HeadControlArbiter` durumunu okur veya pan/tilt ister |
| `GET` / `POST` | `/vlm/people`, `/vlm/person/remember`, `/vlm/person/relationship` | Kilitli kişi hafızası ve ilişki yönetimi |
| `GET` | `/vlm/video_feed` | Talep odaklı açıklamalı MJPEG kamera akışı |
| `GET` | `/vlm/remote_mm/health` | Uzak multimodal GPU sunucusu erişim ve görev ayrımı durumu |

---

## 🧪 Testlerin Çalıştırılması

```bash
pytest tests/modules/vlm_bridge -v
```