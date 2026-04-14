# Diagnostics Modülü Mimarisi

Diagnostics modülü (`modules/diagnostics`), robotun açılış evresinde (POST - Power On Self Test) ve çalışma sırasında periyodik olarak donanım/yazılım bileşenlerinin sağlığını test eden modüldür.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Test Akışı
    START("self_test Başlar") --> CHK_ARDU{"Arduino<br>Ping"}
    CHK_ARDU -- "Timeout" --> FAIL_ARDU("Hata:<br>Arduino Bağlantısı Koptu")
    CHK_ARDU -- "OK" --> CHK_CAM{"Kamera<br>Cevap"}
    
    CHK_CAM -- "Hata" --> FAIL_CAM("Uyarı:<br>Kamera Bulunamadı")
    CHK_CAM -- "OK" --> CHK_LLM{"Ollama<br>Servisi"}
    
    CHK_LLM -- "Kapalı" --> FAIL_LLM("Uyarı:<br>Ollama Yok, Offline Mod")
    CHK_LLM -- "OK" --> FINISH_TEST
    
    FAIL_ARDU --> AGGREGATE
    FAIL_CAM --> AGGREGATE
    FAIL_LLM --> AGGREGATE
    FINISH_TEST --> AGGREGATE
    
    AGGREGATE("Tüm Test Sonuçlarını<br>JSON Olarak Topla") --> CHK_CRIT{"Kritik Hata Var mı?"}
    
    CHK_CRIT -- "Evet (Örn: Arduino)" --> PLAY_ERR("Speak TTS ile 'Kritik sistem hatası' Sentezle<br>NeoPixel KIRMIZI")
    CHK_CRIT -- "Hayır" --> PLAY_OK("Tüm sistemler çevrimiçi<br>NeoPixel YEŞİL")
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    DiagnosticsService ||--o{ ArduinoSerial : pings
    DiagnosticsService ||--o{ OllamaService : pings
    DiagnosticsService ||--o{ CameraService : checks

    DiagnosticsService {
        bool self_test_ok
        string last_report
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Boot Sırası Hata (POST)**
   - Boot esnasında `run_self_test` çağrılır. Testlerin paralel yapılması sistemin donmasını engeller.
   - **`if`** Ollama/AI bağlantısı gibi modüller düşerse (çökerse) bu `CRITICAL` (Kritik) bir hata sayılmaz, sadece `WARNING` üretir. Çünkü robot çevrimdışı komutları ve hareketleri yapmaya devam edebilir (fallback fallback).
   - **`if`** Arduino (Motor denetleyici) seriyoldan düşerse bu `CRITICAL` hatadır, çünkü robotun kasları (servoları ve adım motorları) işlevini yitirmiştir, dengesini kaybedebilir. Anında kırmızı alarm verir ve donanım denge koruma (`E-STOP`) komutu yollar.
