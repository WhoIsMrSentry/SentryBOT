# Speech Modülü Mimarisi

Speech modülü (`modules/voice/speech`), mikrofon verisini alarak konuşma tanıma (ASR/STT) işlemi yapar ve sesin geliş yönünü (direction) tahmin eder.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Ana Giriş
    START([Mikrofon Dinleme Döngüsü]) --> CAPTURE_AUDIO["modules.voice.audio_router<br>(Kilit-Dışı Worker Akışı)"]
    
    %% Ön İşleme ve Ses Yönü
    subgraph Conditioning [Ön İşleme, Echo Gate & Opsiyonel DoA]
        direction TB
        CAPTURE_AUDIO --> PRE["RMS/VU + Downmix + Gain +<br>SoftwareEchoGate (Speak Bağlı)"]
        PRE --> CHK_DIR_SUPPORT{"direction.enabled?"}
        CHK_DIR_SUPPORT -- Evet --> CALC_DOA["DOA - GCC-PHAT -> PanTiltController"]
        CHK_DIR_SUPPORT -- Hayır --> SKIP_DIR["DoA Atlanır (Ön İşleme Devam Eder)"]
    end
    
    %% Konuşma Tanıma
    subgraph Speech_Recognition [Tek Geçişli Mono ASR & Turn-Taking]
        direction TB
        CALC_DOA --> TT["DynamicTurnTakingEngine<br>(channels=1 Mono + Enerji Düşüşü)"]
        SKIP_DIR --> TT
        TT -- "on_turn_cue" --> CUE_HEAD["Kafa İpucu / Hesitation Cue"]
        TT -- "turn_completed" --> SEND_ASR["Recognizer.recognize_pcm() (Tek Google STT)"]
        SEND_ASR --> FIN["finalize_stt(already_transcribed=True)<br>+ SpeakerId İpucu"]
        FIN --> AUTONOMY["/autonomy/speech & OLED Altyazı"]
    end
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    SpeechService ||--o{ AutonomyBrain : provides_data
    WakewordService ||--|| SpeechService : starts_stops

    SpeechService {
        string last_speech_text
        int current_direction_deg
        bool is_listening
    }
    WakewordService {
        string trigger_word
        bool wake_active
    }
    AutonomyBrain {
        string poll_channel
        int poll_interval_ms
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Dinleme Durumu (Enable/Disable)**
   - **`if`** `is_listening == False`: Sensör mikrofonu okumayı bırakmaz ama STT (Speech-to-Text) motoruna göndermez (CPU tasarrufu).
   - Bu durum genelde `Wakeword` modülü tarafından yönetilir (Wakeword duyulunca `is_listening = True` yapılır).
2. **Ses Yönü Hesaplaması (DOA)**
   - **`if`** donanım özel 4-mikrofonlu bir array ise (ReSpeaker gibi), sesin gecikme farklarından (TDOA) açısı hesaplanır (`0 - 360` derece).
   - Bu veri `Autonomy` tarafından saniyede bir poll edilir. **`if`** açı değişimi eski açıdan 15 dereceden fazlaysa, Autonomy kafayı o yöne çevirir.
3. **Kısa/Gürültü Filtrelemesi**
   - **`if`** `len(text.strip()) < 3`: Sadece tek hecelik gürültüler veya öksürükler metin olarak kabul edilmez, silinir.
