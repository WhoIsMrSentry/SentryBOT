# SentryBOT V5 — Agent Core Modülü (`modules/agent_core`)

SentryBOT V5'in merkezi bilişsel beyni, karar orkestratörü ve otonom davranış yöneticisidir. Çok katmanlı zekâ mimarisi (Tri-Layer Architecture), LAYA sosyal yoldaş motoru, eylem güvenlik denetçisi (`ActionArbiter`) ve dünya durumu modelini (`WorldState`) tek bir orkestrasyon çatısı altında birleştirir.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

```bash
# Gerekli Python kütüphaneleri:
pip install fastapi uvicorn requests pydantic pyyaml numpy
```

### 2. Ajan Servisini Başlatma

Agent Core doğrudan Gateway (`:8080`) üzerinden koşabileceği gibi bağımsız bir mikroservis olarak da başlatılabilir:

```bash
python -m modules.agent_core.xAgentCoreService
```

---

## 📂 Dizin Yapısı

```
modules/agent_core/
├── xAgentCoreService.py              # Bağımsız Servis Başlatıcı
├── config_loader.py                  # YAML Yapılandırma Yükleyici
├── architecture_agent_core.dot       # Graphviz Mimari Diyagram Kaynağı
├── architecture_agent_core.svg       # Derlenmiş Vektörel Mimari Şema
├── architecture_agent_core.md        # Kapsamlı Teknik & Sınıf Referansı
├── README.md                         # Bu doküman
├── api/                              # FastAPI Yönlendiricileri (/agent/*)
├── domain/                           # Alan Modelleri ve Veri Yapıları
└── services/                         # Bilişsel ve Eylemsel Servisler
    ├── agent.py                      # AgentOrchestrator (Merkezi Karar Döngüsü)
    ├── tri_layer.py                  # Tri-Layer Router (Refleks, Taktik, Stratejik)
    ├── laya_engine.py                # LAYA Sosyal Yoldaş & Dolgu Cümlesi Motoru
    ├── action_arbiter.py             # Eylem Eşzamanlılık ve Kaynak Hakemi
    ├── safety_filter.py              # Donanım Açı ve Hız Güvenlik Kırpıcısı (Clamping)
    ├── speech_arbiter.py             # Öncelikli Konuşma Kuyruğu & Barge-In
    ├── world_state.py                # Merkezi Dünya Durumu & Prompt Enjeksiyonu
    ├── progress.py                   # Çok Adımlı Hedef İlerleme Takibi (TR/EN)
    ├── semantic_index.py             # TF-IDF Anlamsal Epizodik Bellek Arama
    ├── slam.py                       # 2D Grid Haritalama ve A* Yol Bulucu
    └── tools/                        # Ajan Araçları (Hareket, Algı, Donanım)
```

---

## 🧠 Üç Katmanlı Bilişsel Mimari (Tri-Layer)

1. **Katman 1: Hızlı Refleks (<50 ms):** Acil durdurma, selamlama ve ani uyanma refleksleri.
2. **Katman 2: Taktik Planlama (50-300 ms):** Araç yürütme, engel aşma, kafa yönlendirme ve kısa yanıtlar.
3. **Katman 3: Stratejik Muhakeme (>300 ms):** Çok adımlı derin akıl yürütme, LLM zincirleri ve uzun vadeli planlama.

---

## 💻 Python Kullanım Örnekleri

### 1. AgentOrchestrator ile Adım Yürütme
```python
from modules.agent_core.services.agent import AgentOrchestrator

orchestrator = AgentOrchestrator()

# Bir karar adımı koştur
response = orchestrator.step("Etrafı tara ve şüpheli bir şey var mı bak.")
print("Ajan Cevabı:", response.get("speech"))
print("Yürütülen Eylemler:", response.get("actions"))
```

### 2. Güvenli Eylem Denetimi (`SafetyFilter`)
```python
from modules.agent_core.services.safety_filter import SafetyFilter

safety = SafetyFilter()

# Aşırı servoyu güvenli sınıra (10-170 derece) kırpar
clamped_deg = safety.clamp_servo(index=0, deg=210.0)
print("Kırpılmış Güvenli Açı:", clamped_deg) # 170.0
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. Akıllı Diyalog ve Görev Yürütme
```bash
curl -X POST http://127.0.0.1:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Devriye moduna geç ve çevreyi izle."}'
```

### 2. Konuşmayı Anında Kesme (Barge-In)
```bash
curl -X POST http://127.0.0.1:8080/agent/speech/interrupt
```

### 3. Ajan ve Dünya Durumunu Sorgulama
```bash
curl -X GET http://127.0.0.1:8080/agent/status
```

---

## 🧪 Testleri Çalıştırma

Tri-layer router, LAYA motoru, güvenlik süzgeci ve anlamsal bellek testlerini koşturmak için:

```bash
pytest tests/modules/agent_core -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_agent_core.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/agent_core/architecture_agent_core.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_agent_core.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/agent_core/architecture_agent_core.dot): Graphviz formatında modüler bilişsel beyin çizimi.
- [architecture_agent_core.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/agent_core/architecture_agent_core.svg): Vektörel mimari şeması.