# SentryBOT V5 — İfade Modülü (`modules/expression`)

SentryBOT V5'in robotik bedenindeki tüm jest ve mimikleri, yüz ifadelerini (OLED), RGB aydınlatmayı (NeoPixel), kafa hareketlerini ve kulak servolarını tek bir duygusal odakta birleştiren merkezi koreografi alt sistemidir.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

```bash
# Gerekli Python kütüphaneleri:
pip install fastapi uvicorn requests pyyaml numpy
```

---

## 📂 Dizin Yapısı

```
modules/expression/
├── architecture_expression.dot       # Graphviz Mimari Diyagram Kaynağı
├── architecture_expression.svg       # Derlenmiş Vektörel Mimari Şema
├── architecture_expression.md        # Kapsamlı Teknik & Sınıf Referansı
├── README.md                         # Bu doküman
├── semantic/                         # Anlamsal İfade Direktörü & Arbitraj
│   ├── xExpressionService.py         # Çok Modlu Duygu Yöneticisi
│   └── services/arbitrator.py        # Görsel Kilit & Şiddet Ölçekleyici
├── interactions/                     # Sistem Olayları & Olay Yönlendirici
│   ├── xInteractionsService.py       # Olay Dinleme ve Sessiz Saatler Filtresi
│   └── services/                     # Kural Tabanlı Tetikleyiciler
├── animate/                          # Anahtar Kare ve Prosedürel Hareket
│   ├── xAnimateService.py            # Poz Motoru (sit, stand, stretch, nod)
│   └── services/procedural_motion.py # Doğal Nefes Alma ve Kafa Salınımı
└── piservo/                          # Kulak Servoları & İşitsel Refleks
    ├── xPiServoService.py            # PCA9685 / PWM Donanım Sürücüsü
    └── services/ear_reflex.py        # Sese Yönelme & Duygusal Kulak Pozları
```

---

## 🎭 Çok Modlu İfade Kanalları

Bir duygu tetiklendiğinde (`/expression/express`), sistem şu 4 kanalı eşzamanlı olarak senkronize eder:
1. **OLED Gözler (`visual_output/oled_faces`):** Duyguya uygun göz şekli çizilir.
2. **RGB LED'ler (`visual_output/neopixel`):** Duygu paletine uygun renk nabzı oynatılır.
3. **Kulak Servoları (`expression/piservo`):** Kulaklar dikleşir veya geriye yatar.
4. **Kafa Pozu (`expression/animate`):** Baş hafifçe onaylar veya yana eğilir.

---

## 💻 Python Kullanım Örnekleri

### 1. Çok Modlu Duygusal İfade Tetikleme
```python
from modules.expression.semantic.xExpressionService import xExpressionService

expr_service = xExpressionService()

# Mutluluk ifadesi oynat (Gözler güler, sarı LED nabzı, kulaklar dikleşir)
expr_service.express(emotion="happy", intensity=0.85, duration_s=3.0)
```

### 2. Prosedürel Poz Oynatma
```python
from modules.expression.animate.xAnimateService import xAnimateService

anim = xAnimateService()

# Onaylama hareketi (Baş sallama)
anim.run_pose("nod", duration_ms=1000)
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. Bütünleşik Duygu İfadesi
```bash
curl -X POST http://127.0.0.1:8080/expression/express \
  -H "Content-Type: application/json" \
  -d '{"emotion": "happy", "intensity": 0.9, "duration_s": 2.5}'
```

### 2. Kulak Pozisyonu Ayarlama
```bash
curl -X POST http://127.0.0.1:8080/expression/ears \
  -H "Content-Type: application/json" \
  -d '{"left_deg": 120.0, "right_deg": 60.0}'
```

### 3. İfade Durumu ve Aktif Kilit Kontrolü
```bash
curl -X GET http://127.0.0.1:8080/expression/status
```

---

## 🧪 Testleri Çalıştırma

İfade direktörü, etkileşim yönlendirici, animasyon ve kulak refleksi testlerini koşturmak için:

```bash
pytest tests/modules/expression -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_expression.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/expression/architecture_expression.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_expression.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/expression/architecture_expression.dot): Graphviz formatında modüler ifade alt sistemi çizimi.
- [architecture_expression.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/expression/architecture_expression.svg): Vektörel mimari şeması.