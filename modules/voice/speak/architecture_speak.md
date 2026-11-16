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
    subgraph Engine Selection [TTS Motoru Secimi]
        direction TB
        CHK_ENGINE -- Piper / Yerel --> ENGINE_PIPER(Piper ONNX / PersistentPiperModel)
        CHK_ENGINE -- Remote / XTTS HTTP --> ENGINE_REMOTE(RemoteTTSHttpBackend / XTTSHttpBackend)
        CHK_ENGINE -- Dummy (test) --> ENGINE_DUMMY(DummyBackend - SENTRYBOT_ALLOW_TEST_TTS=1)
    end
    
    ENGINE_REMOTE -- Hata (iptal değilse) --> ENGINE_PIPER
    ENGINE_PIPER --> APPLY_TONE
    ENGINE_REMOTE --> APPLY_TONE
    ENGINE_DUMMY --> APPLY_TONE
    
    %% Duygusal Tonlama ve Sentezleme
    subgraph Tone Application [Duygu / Ton Ayarlama]
        direction TB
        APPLY_TONE --> CHK_TONE{"Tone Değeri: <br> 'happy', 'sad', 'angry' ..."}
        
        CHK_TONE -- happy --> SET_H[Hız: +%20, Ses: +%10] --> SYNTHESIZE
        CHK_TONE -- sad --> SET_S[Hız: -%25, Ses: -%20] --> SYNTHESIZE
        CHK_TONE -- angry --> SET_A[Hız: +%10, Ses: MAX] --> SYNTHESIZE
        CHK_TONE -- neutral / Yok --> SET_N[Normal Hız ve Ses] --> SYNTHESIZE
        
        SYNTHESIZE(TTS Sentezi -> LRU PCM Önbelleği ve <br> AudioPlayer ile Oynatma + Asenkron @gateway/expression)
    end
    
    SYNTHESIZE --> DONE([ok: true])
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    AutonomyBrain ||--o{ SpeakService : generates_speech
    VisionBridge ||--o{ SpeakService : pushes_alerts
    SpeakService ||--o{ SpeechPriorityQueue : serializes_streams

    SpeakService {
        string default_engine
        int rate
        string language
        int pcm_cache_max_entries
    }
```

## ⚙️ Detaylı Karar Mantığı

1. **Metin Temizliği & Çevrimdışı Dil Algılama (`lang_detect.py`)**
   - Autonomy'den gelen LLM cümlesi markdown, kod bloğu veya iç düşünce etiketleri (`<think>`, `reasoning:` vb.) barındırıyorsa okunmadan önce temizlenir.
   - `resolve_speak_language()` ağ sondası olmadan (`1.1.1.1:53` yok) metin dilini algılar; sayı/noktalama gibi belirsiz metinlerde `explicit` oturum dilini korur.
2. **Öncelikli Akış Kuyruğu & Kesintisiz Barge-In (`SpeechPriorityQueue` & `AudioPlayer`)**
   - `/speak/say_stream` cümleleri tek işçili sıralı `SpeechPriorityQueue` üzerinden oynatılır; yüksek öncelikli akış geldiğinde aktif konuşma anında kesilir.
   - `AudioPlayer.stop_playback()` kilitsizdir (`_play_lock` beklemeden `_play_stop.set()` ve `sd.stop()` çağırır); `stop()` ve `stop_speaking()` sentezi iptal edip `speak.finished` bildirimini asenkron yayımlar.
3. **Motor Seçimi & LRU PCM Önbelleği (`TextToSpeech`)**
   - Kısa ve sık kullanılan ifadeler (`<= 80` karakter, en fazla `24` kayıt) LRU `_pcm_cache` içinden tekrar sentezlemeden döndürülür.
   - Uzak (`remote`/`xtts`) hata verirse önbellekli yerel `PiperBackend`'e düşer; ancak kullanıcı barge-in (`synthesis_cancelled`) nedeniyle iptal edildiyse fallback tetiklenmez.
