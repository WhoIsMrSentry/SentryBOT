# Speak (TTS) Modülü Mimarisi

Speak modülü (`modules/speak`), metinden sese dönüştürme (Text-to-Speech) işlemini gerçekleştirerek robotun fiziksel hoparlöründen konuşmasını sağlar.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Ana Giriş
    API_REQ([POST /speak/say]) --> PARSE_REQ(Gelen parametreler: <br> text, tone, engine)
    
    PARSE_REQ --> CHK_TEXT{"Metin/Text <br> Boş mu?"}
    
    %% API Kontrolleri
    subgraph TTS Request Validation [İstek Doğrulama & Temizlik]
        direction TB
        CHK_TEXT -- Evet --> RET_ERR([Hata: Text Gerekli])
        CHK_TEXT -- Hayır --> CLEAN_TEXT(Regex ile Markdown <br> ve JSON Artıklarını Temizle)
        CLEAN_TEXT --> CHK_ENGINE{"Hangi Motor?"}
    end
    
    %% Motor Seçimi
    subgraph Engine Selection [TTS Motoru Seçimi]
        direction TB
        CHK_ENGINE -- Default / pyttsx3 --> ENGINE_PYTTS(pyttsx3)
        CHK_ENGINE -- Piper --> ENGINE_PIPER(Piper / Offline Türkçe)
        CHK_ENGINE -- Diğer (espeak, vb.) --> ENGINE_DEF(Fallback Engine)
    end
    
    ENGINE_PYTTS --> APPLY_TONE
    ENGINE_PIPER --> APPLY_TONE
    ENGINE_DEF --> APPLY_TONE
    
    %% Duygusal Tonlama ve Sentezleme
    subgraph Tone Application [Duygu / Ton Ayarlama]
        direction TB
        APPLY_TONE --> CHK_TONE{"Tone Değeri: <br> 'happy', 'sad', 'angry' ..."}
        
        CHK_TONE -- happy --> SET_H[Hız: +%20, Ses: +%10] --> SYNTHESIZE
        CHK_TONE -- sad --> SET_S[Hız: -%25, Ses: -%20] --> SYNTHESIZE
        CHK_TONE -- angry --> SET_A[Hız: +%10, Ses: MAX] --> SYNTHESIZE
        CHK_TONE -- neutral / Yok --> SET_N[Normal Hız ve Ses] --> SYNTHESIZE
        
        SYNTHESIZE(TTS Sentezleme ve <br> ALSA / aplay ile Oynatma)
    end
    
    SYNTHESIZE --> DONE([ok: true])
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    AutonomyBrain ||--o{"SpeakService : generates_speech
    VisionBridge ||--o{ SpeakService : pushes_alerts
    
    SpeakService {
        string default_engine
                float base_rate
                say_text__tone"}
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Metin Temizliği (Regex)**
   - Autonomy'den gelen LLM cümlesi yanlışlıkla markdown yıldızları (`*hızla kafa sallar*`), etiketler (`<speak>`) barındırıyorsa, okumadan önce Regex ile bunları temizler (`re.sub` mantığı). Aksi takdirde TTS motoru harf harf "yıldız gülücük yıldız" şeklinde okur.
2. **Tone (Duygu) Ayarlamaları**
   - Autonomy Brain, robotun hissettiği duyguya (joy, sadness) göre `tone` parametresini doldurur.
   - **`if`** `tone == 'sad'`: Hoparlörün okuma hızı (rate) düşürülür, ses (volume) azaltılır, böylece mutsuz bir tını oluşur.
   - **`if`** `tone == 'happy'`: Cümle ritmik ve daha hızlı, sesi daha gür çıkar.
3. **Motor Seçimi (`pyttsx3` vs `piper`)**
   - **`if`** `engine == 'piper'`: RPi üzerinde yüksek kaliteli yerel insan sesi sentezleyen piper binary'sini (`subprocess` ile) çalıştırıp `aplay` (ALSA ses sistemi) portuna pipe eder.
   - **`else`**: Basit ama uyumlu olan standart `pyttsx3` nesnesi (runAndWait) çağrılır.
