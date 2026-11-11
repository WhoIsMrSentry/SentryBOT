# PiServo Modülü Mimarisi

PiServo modülü (`modules/piservo`), Arduino'ya harici olarak bağlanamayan veya gövdeden bağımsız kafada (Raspberry Pi üzerinde) bulunan özel donanımları (Örn: Kulak servoları) doğrudan Pi'nin GPIO PWM pinleri üzerinden kontrol eden sınıftır.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    REQ_SRV("POST /piservo/set") --> VALIDATE("Açı Doğrulama (finite & min..max)")
    VALIDATE --> RAMP("EarRunner (~50 Hz Ramp + RLock)")
    RAMP --> BACKEND{"Aktif Paylaşımlı Backend?"}
    BACKEND -- "pigpio" --> PIG("_PigpioWrapper (tek pi örneği)")
    BACKEND -- "lgpio (RPi 5)" --> LGP("_LgpioWrapper (tek gpiochip handle)")
    BACKEND -- "yok (dev/test)" --> SIM("_SimGPIO")
    PIG & LGP & SIM --> DETACH("idle_detach_ms sonrası PWM=0")
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    EarRunner ||--|| SharedGpioBackend : shares_across_ears
    EarRunner ||--|| EarReflexEngine : acoustic_doa_reflex
    AutonomyBrain ||--o{ EarRunner : sends_gestures_or_emotions

    EarRunner {
        float center_deg
        int idle_detach_ms
        float max_speed_deg_s
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Tek Paylaşımlı Backend & Lifespan Temizliği**
   - Sol (GPIO 12) ve sağ (GPIO 13) kulak tek bir paylaşılan `_PigpioWrapper` / `_LgpioWrapper` / `_SimGPIO` örneği kullanır. FastAPI `lifespan` kapanışında `runner.close()` tüm zamanlayıcıları durdurur, PWM'i `0` yapıp chip/pigpio tanıtıcısını kapatır.
2. **Yumuşak Ramp & `idle_detach_ms` PWM Kapatma**
   - Hedefe yumuşak ~50 Hz adım atıldıktan ve konum oturduktan `idle_detach_ms` ms sonra PWM kapatılarak SG90/MG90S servolarda vızıltı ve ısınma engellenir; bilinmeyen veya `NaN` girdiler HTTP 400 ile reddedilir.
