# Speech Modülü Mimarisi

Speech modülü (`modules/voice/speech`), mikrofon verisini alarak konuşma tanıma (ASR/STT) işlemi yapar ve sesin geliş yönünü (direction) tahmin eder.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Ana Giriş
    START([Mikrofon Dinleme Döngüsü]) --> CAPTURE_AUDIO[Ses Akışını Yakala]
    
    %% Ses Yönü Bulma
    subgraph Direction_Calculation [Ses Yönü Tahmini]
        direction TB
        CAPTURE_AUDIO --> CHK_DIR_SUPPORT{"Cihaz Çok Kanallı mı? <br> (Örn: ReSpeaker)"}
        CHK_DIR_SUPPORT -- Evet --> CALC_DOA(DOA - Direction of Arrival <br> Hesapla)
        CHK_DIR_SUPPORT -- Hayır --> SKIP_DIR[Varsayılan 0° / İleri]
        
        CALC_DOA --> SET_DIR_VAR[Global Ses Yönü Değişkenini<br>Güncelle]
        SKIP_DIR --> SET_DIR_VAR
    end
    
    %% Konuşma Tanıma
    subgraph Speech_Recognition [Konuşma Tanıma ASR]
        direction TB
        SET_DIR_VAR --> VAD_CHK{"Ses Var mı? <br> Voice Activity Detection"}
        
        VAD_CHK -- Hayır --> SESSİZLIK((Bekle)) --> CAPTURE_AUDIO
        VAD_CHK -- Evet --> SEND_ASR[Ses Verisini <br> Recognizer Motoruna İlet]
        
        SEND_ASR --> RECOGNIZER_ENGINE(Vosk / Whisper / Google)
        
        RECOGNIZER_ENGINE --> PARSE_RES{"Motor Sonuç <br> Döndürdü mü?"}
        PARSE_RES -- Hayır / Gürültü --> SESSİZLIK
        PARSE_RES -- Evet --> EXTRACT_TEXT[Tanınan Metni Al]
        
        EXTRACT_TEXT --> SET_LAST_SPEECH(last_speech_text <br>değişkenini güncelle)
    end
    
    SET_LAST_SPEECH --> AUTONOMY_PULL[Autonomy Modülü<br>Tarafından Poll Edilmeyi Bekle]
    AUTONOMY_PULL --> SESSİZLIK
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
