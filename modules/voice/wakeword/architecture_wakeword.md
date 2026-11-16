# Wakeword Modülü Mimarisi

Wakeword modülü (`modules/wakeword`), arka planda sürekli olarak dinleyerek robotun aktivasyon kelimesini (örn: "Hey Sentry", "Alexa", "Jarvis") algılayan düşük güç tüketimli bir tetikleyicidir.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Ana Giriş
    START([Arka Plan Dinleme Thread'i]) --> SETUP_WW_ENGINE(AudioRouter + OpenWakewordRunner<br>ONNX / TFLite Başlat)
    
    SETUP_WW_ENGINE --> WAIT_AUDIO["AudioCapture.stream(stop_event)<br>Kilit-Dışı Worker Kuyruğu"]
    
    %% Arka Plan Döngüsü
    subgraph Background Listening [Enerji Kapılı Sürekli Dinleme]
        direction TB
        WAIT_AUDIO --> RMS_GATE{"RMS / SharedVAD<br>Aktivite Var mı?"}
        RMS_GATE -- Hayır --> DISCARD_CHUNK[ONNX Atla / CPU Koru] --> WAIT_AUDIO
        RMS_GATE -- Evet --> CHK_WAKEWORD{"OpenWakewordRunner:<br>Uyandırma Algılandı mı?"}
        CHK_WAKEWORD -- Hayır --> WAIT_AUDIO
        CHK_WAKEWORD -- Evet --> TRIGGER_ACT("Wakeword Algılandı <br> _on_wakeword")
    end
    
    %% Tetikleme Sonrası İşlemler
    subgraph Trigger Actions [Tetikleme & Barge-In]
        direction TB
        TRIGGER_ACT --> INTERRUPT["interrupt_robot_speech() <br> Speak Stop + Agent Interrupt"]
        INTERRUPT --> START_SPEECH_API["start_speech() & emit_event('wakeword.detected')"]
        START_SPEECH_API --> START_WINDOW["Komut Penceresi (listen_window_sec)"]
        START_WINDOW --> FINAL_CHK{"stop_on_final &<br>has_final_speech()?"}
        FINAL_CHK -- Evet / Süre Doldu --> STOP_SPEECH_API["stop_speech()"]
    end
    
    STOP_SPEECH_API --> WAIT_AUDIO
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    WakewordService ||--|| SpeechService : activates
    WakewordService ||--o{ InteractionEngine : pushes_events
    WakewordService ||--o{ AutonomyBrain : updates_status

    WakewordService {
        string model_path
        int command_window_s
    }
    SpeechService {
        bool is_listening
        string trigger_source
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Dinleme Aktivasyonu (`_on_wakeword()`)**
   - Wakeword duyulduğunda, **`if`** `command_window_s > 0` (dinleme penceresi yapılandırılmışsa):
     - `Speech` motoruna bağlanarak metin dönüştürmeyi (ASR) aktif hale getirir. (Bu sayede mikrofon her saniye buluta / CPU ağır modellere ses yollamaz, sadece wakeword'den sonraki 5 saniye STT çalışır).
   - Ayrıca robotun uyandığını belli etmek için `Interactions` modülüne bir event basar. (Bu da LED'leri mavi yakıp söndürür).
2. **Kapatma Zamanlayıcısı (Timeout)**
   - `threading.Timer` başlatılır.
   - **`if`** 5 saniye içinde başka bir komut verilirse (Autonomy metni çoktan aldıysa) motor kapanır.
   - **`else`**: Süre dolsa bile komut bitmemişse bile acımasızca `Speech/Stop` çağrısı yaparak batarya ve CPU'yu korur.
