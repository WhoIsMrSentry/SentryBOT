# SentryBOT — Mimari Özet (Architecture Summary)

> AI asistanlar bu dosyayı okuyarak sistemin büyük resmini anlar. Detaylar için `docs/ARCHITECTURE.md` dosyasına bakın.

## Sistem Genel Bakışı

SentryBOT, Raspberry Pi 5 üzerinde çalışan, modüler mikro-servis mimarisine sahip otonom bir robot platformudur. Arduino ile seri iletişim, OpenCV ile görüntü işleme, Ollama LLM ile yapay zekâ yetenekleri entegre eder.

## 5 Katmanlı Mimari

```mermaid
flowchart TB
    subgraph L1["1. ALGI KATMANI"]
        camera["Camera<br/>MJPEG stream"]
        speech["Speech<br/>ASR + DOA"]
        vlm["VLM Bridge<br/>Yüz algılama"]
        wakeword["Wakeword<br/>Hey Sentry"]
        hw["Hardware<br/>CPU/RAM/Temp"]
    end

    subgraph L2["2. BEYİN KATMANI"]
        gateway["Gateway<br/>API Bootstrapper<br/>Port 8080"]
        autonomy["Autonomy<br/>Sense-Think-Act"]
        agent["Agent Core<br/>3-Layer Agent"]
        state["State Manager<br/>Thread-safe store"]
        config_c["Config Center<br/>Hot-reload"]
    end

    subgraph L3["3. AI / RAG KATMANI"]
        ollama["Ollama<br/>LLM Chat<br/>Port 8099"]
    end

    subgraph L4["4. EYLEM KATMANI"]
        arduino["Arduino Serial<br/>NDJSON komut"]
        animate_m["Animate<br/>YAML servo"]
        neo["NeoPixel<br/>LED animasyon"]
        speak_m["Speak (TTS)<br/>Port 8083"]
        piservo["PiServo<br/>GPIO PWM"]
        oled["OLED Faces"]
    end

    subgraph L5["5. ARKA PLAN"]
        sched["Scheduler"]
        diag["Diagnostics"]
        log_m["Logwrapper"]
        telem["Telemetry"]
        ota_m["OTA Update"]
        notif["Notifier"]
    end

    L1 --> L2
    L2 --> L3
    L3 --> L2
    L2 --> L4
    L4 --> L5
```

## Temel Veri Akışı

```
Wakeword ──trigger──→ Speech (ASR açılır)
Speech ──metin──→ Autonomy (Sense aşaması)
Camera ──frame──→ VLM Bridge (yüz algılama)
VLM Bridge ──kişi bilgisi──→ Autonomy (mood güncelle)
Autonomy ──soru──→ Ollama (LLM chat)
Ollama ──yanıt + actions──→ Autonomy (Act aşaması)
Autonomy ──HTTP──→ Speak (TTS), NeoPixel (LED), Animate (servo)
Animate/VLM ──serial──→ Arduino Serial ──NDJSON──→ Arduino
Interactions ──kural motoru──→ NeoPixel
```

## Gateway Bootstrap Mekanizması

1. `run_robot.py` → `create_app()` çağırır
2. `bootstrap(app, cfg)` → `config.yml`'deki `include` sözlüğünü okur
3. Her `include.<module>: true` için `_include_<module>(app, cfg)` çağrılır
4. Modül başarısızsa → warning loglanır, diğer modüller devam eder
5. Tüm modüller bağımsız çalışır (Microservice Pattern)

## Agent Core — 3 Katmanlı Ajan

```
Layer 1: Router/Planner → İsteği uygun sub-agent'lara yönlendirir
Layer 2: Module Sub-Agent → Domain-specific tool çalıştırır
Layer 3: Main Persona → Tutarlı final cevap üretir
```

Tüm katmanlar aynı Ollama modeli üzerinden çalışır (tek model stratejisi: `qwen3.5:9b`).

## Autonomy — Sense-Think-Act Döngüsü

```
SENSE → Konuşma var mı? Ses yönü değişti mi? Kişi görüldü mü?
THINK → Duygu bozunması, sıkılma kontrolü, uyku saati kontrolü
ACT   → LLM yanıtını parse et, donanım HTTP çağrıları yap
```

### Duygusal Model (Affective Model)

- **Mood eksenleri:** happiness, energy, curiosity, fear, **anger** (öfke ekseni
  `anger>45 → anger`, `anger>75 → furious` baskın duygularını üretir).
- **Affective appraisal** (`services/affective_appraisal.py` + `config/appraisal.yml`):
  semantik olayları (`user_rude`, `owner_returned`, `command_failed`…) mood
  deltalarına çevirir → duygular zamansal bozunmadan değil **nedenden** doğar.
- **Tek duygu sözlüğü:** tüm görsel/işitsel çıktılar `modules/common` kanonik
  duygu vocab'ından çözülür (eyes/LEDs/ears/tone aynı taksonomi).
- **Expression Director** (`services/expression_director.py`): tek çağrıda
  gözler + LED + kulaklar + kafa + ses tonunu eşgüdümlü tetikler (`brain.express`).

## Güvenlik ve Dayanıklılık

- **Owner kontrolü:** VLM + RFID ile sahip doğrulaması
- **LLM fallback:** JSON parse başarısızsa → regex ile XML tag ayrıştırma
- **CPU throttling:** VLM FPS sınırı, Wakeword hafif işlem
- **API timeout:** ServiceClient üzerinde 1s timeout → modül çökse bile robot hayatta
- **Safety filter:** Servo açı sınırları, stepper hız limiti, lazer süre limiti
