# Wakeword Modülü Mimarisi

Wakeword modülü (`modules/wakeword`), arka planda sürekli olarak dinleyerek robotun aktivasyon kelimesini (örn: "Hey Sentry", "Alexa", "Jarvis") algılayan düşük güç tüketimli bir tetikleyicidir.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Ana Giriş
    START([Arka Plan Dinleme Thread'i]) --> SETUP_WW_ENGINE(Wakeword Motorunu Başlat <br> Porcupine / Snowboy)
    
    SETUP_WW_ENGINE --> WAIT_AUDIO[Mikrofondan Küçük<br>PCM Chunk'lar Oku]
    
    %% Arka Plan Döngüsü
    subgraph Background Listening [Srekli Dinleme ve Tetikleme]
        direction TB
        WAIT_AUDIO --> CHK_WAKEWORD{"Motor: 'Hey Sentry'<br>dedi mi?"}
        
        CHK_WAKEWORD -- Hayır --> DISCARD_CHUNK[Sesi Çöpe At] --> WAIT_AUDIO
        
        CHK_WAKEWORD -- Evet --> TRIGGER_ACT(Wakeword Algılandı <br> '_on_wakeword')
    end
    
    %% Tetikleme Sonrası İşlemler
    subgraph Trigger Actions [Tetikleme Aksiyonları]
        direction TB
        TRIGGER_ACT --> START_SPEECH_API(POST /speech/start <br> Konuşma Tanımayı Aç)
        START_SPEECH_API --> PUSH_EVENT(POST /interactions/event <br> 'wakeword.detected')
        
        PUSH_EVENT --> SOUND_CB{"Bip Sesi <br> Açıksa"}
        SOUND_CB -- Evet --> ARDU_BEEP(POST /arduino/send <br> buzzer bip)
        SOUND_CB -- Hayır --> START_WINDOW(Komut Dinleme Süresi Başlat)
        
        ARDU_BEEP --> START_WINDOW
        
        START_WINDOW --> TIMER_WAIT{"Bekle:<br>command_window_s <br>(Örn: 5 sn)"}
        
        TIMER_WAIT -- Süre Dolduğunda --> STOP_SPEECH_API(POST /speech/stop <br> Konuşma Tanımayı Kapat)
    end
    
    STOP_SPEECH_API --> WAIT_AUDIO
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    WakewordService ||--|| SpeechService : activates
    WakewordService ||--o{"InteractionEngine : pushes_events
    WakewordService ||--o{ AutonomyBrain : updates_status
    
    WakewordService {
        string model_path
                int command_window_s
                _on_wakeword"}
    
    SpeechService {start
                stop}
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
