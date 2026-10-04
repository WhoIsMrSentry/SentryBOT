# SentryBOT V5 — Otonomi Modülü (`modules/autonomy`)

SentryBOT V5'in bağımsız yaşam motoru ve otonom davranış beynidir. Robotun içsel ihtiyaçlarını (`living_needs`), duygusal durumunu (`mood`), görsel/işitsel dikkat haritasını (`saliency_map`) ve topolojik harita navigasyonunu yöneterek robotun canlı bir yoldaş gibi kendi kendine hedefler üretmesini sağlar.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

```bash
# Gerekli Python kütüphaneleri:
pip install fastapi uvicorn requests pydantic pyyaml numpy
```

### 2. Otonomi Servisini Başlatma

Otonomi döngüsü Gateway (`:8080`) üzerinden koşturulabileceği gibi bağımsız olarak da başlatılabilir:

```bash
python -m modules.autonomy.xAutonomyService
```

---

## 📂 Dizin Yapısı

```
modules/autonomy/
├── xAutonomyService.py              # Otonomi Servis Başlatıcı
├── config_loader.py                 # YAML Yapılandırma Yükleyici
├── architecture_autonomy.dot        # Graphviz Mimari Diyagram Kaynağı
├── architecture_autonomy.svg        # Derlenmiş Vektörel Mimari Şema
├── architecture_autonomy.md         # Kapsamlı Teknik & Sınıf Referansı
├── README.md                        # Bu doküman
├── api/                             # FastAPI Yönlendiricileri (/autonomy/*)
├── tools/                           # Otonomi Eylem Araçları
└── services/                        # Temel Yaşam ve Karar Motorları
    ├── living_needs.py              # Homeostatik İhtiyaçlar Modeli (Energy, Social, Curiosity)
    ├── needs_engine.py              # İhtiyaç Bozunumu ve Dengeleme Döngüsü
    ├── mood.py                      # 2D Değerlik-Uyarılma (Valence-Arousal) Duygu Motoru
    ├── companion_goal_selector.py   # Proaktif Otonom Hedef Seçici
    ├── companion_auto_execute_gate.py # Güvenli Otomatik Yürütme Kapısı
    ├── companion_lines.py           # Kendiliğinden Spontane Konuşma İfadeleri
    ├── companion_rituals.py         # Günlük Selamlama ve Uyku Ritüelleri
    ├── system1_reflex.py            # Sub-50ms Hızlı Engel ve Tehlike Refleksi
    ├── topomap_motion_executor.py   # Topolojik Graf Navigasyonu
    ├── saliency_map.py              # Görsel Dikkat ve Odak Sıralayıcısı
    └── scene_register.py            # Çevresel Nesne Konum Hafızası
```

---

## 💡 Temel Yetenekler

- **Canlı İhtiyaçlar (Living Needs):** Robotun sosyal ilgi ve keşif merakı zamanla artar; kendi kendine sahibini arar veya etrafı inceler.
- **Duygusal Tepkisellik (Affective Appraisal):** Olaylara göre anlık duygu değişimi yaşar (tanıdık yüz $\rightarrow$ sevinç, yüksek gürültü $\rightarrow$ alarm).
- **Spontane Yoldaş Sözleri:** Kullanıcı sormasa da ortam durumuna uygun samimi yorumlar yapar.
- **Topolojik Devriye:** Haritalandırılmış oda noktaları arasında güvenli otonom serbest dolaşım.

---

## 💻 Python Kullanım Örnekleri

### 1. İhtiyaç Motoru ve Durum Sorgulama
```python
from modules.autonomy.services.living_needs import LivingNeedsState
from modules.autonomy.services.needs_engine import NeedsEngine

engine = NeedsEngine()
state = engine.get_state()

print("Sosyal İhtiyaç Seviyesi:", state.social)
print("Merak Seviyesi:", state.curiosity)

# Sahibini gördüğünde sosyal ihtiyacı tatmin et
engine.satisfy_need("social", 0.4)
```

### 2. Otonom Hedef Belirleme
```python
from modules.autonomy.services.companion_goal_selector import CompanionGoalSelector

selector = CompanionGoalSelector()
goal = selector.select_next_goal()

if goal:
    print(f"Yeni Otonom Hedef: {goal.name} (Öncelik: {goal.priority})")
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. Otonomi Durumunu ve Aktif Hedefi Alma
```bash
curl -X GET http://127.0.0.1:8080/autonomy/status
```

### 2. Canlı İhtiyaç Seviyelerini Sorgulama
```bash
curl -X GET http://127.0.0.1:8080/autonomy/needs
```

### 3. Otonom Döngüyü Duraklatma / Başlatma
```bash
curl -X POST http://127.0.0.1:8080/autonomy/stop
curl -X POST http://127.0.0.1:8080/autonomy/start
```

---

## 🧪 Testleri Çalıştırma

İhtiyaç motoru, duygu alanı, topomap navigasyonu ve hedef seçici testlerini koşturmak için:

```bash
pytest tests/modules/autonomy -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_autonomy.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/autonomy/architecture_autonomy.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_autonomy.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/autonomy/architecture_autonomy.dot): Graphviz formatında modüler otonomi motoru çizimi.
- [architecture_autonomy.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/autonomy/architecture_autonomy.svg): Vektörel mimari şeması.