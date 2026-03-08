# Interactions Modülü Mimarisi

Interactions modülü (`modules/interactions`), robotun pasif ve anlık tepkilerini kural tabanlı (rule-based) olarak yöneten arka plan motorudur. CPU sıcaklığı yükseldiğinde ışıkları kırmızı yapma, internet üzerinden yoğun indirme yaparken gözleri "Yükleniyor (wave)" animasyonuna sokma veya dışarıdan rastgele olaylar geldiğinde LED'leri tetikleme işlerinden sorumludur.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Sistemin her 1-2 saniyede bir ölçüm (metrik) alarak kuralları sırayla (if/else zinciri gibi) nasıl değerlendirdiğini gösteren diyagram:

```mermaid
flowchart TD
    START((Tick Timer <br> Her 1 saniye)) --> GATHER_METRICS
    
    %% Metrik Toplama
    subgraph SENSE_METRICS [Metrik Toplama MetricsCollector]
        direction TB
        GATHER_METRICS[Sistem Verilerini Oku] --> CPU_T(CPU Sıcaklık)
        GATHER_METRICS --> CPU_L(CPU Yük %si)
        GATHER_METRICS --> NET_T(Ağ Trafiği / Burst)
        GATHER_METRICS --> ARDU_C{Arduino <br>Heartbeat<br>Aktif mi?}
        
        ARDU_C -- Evet --> ARDU_OK[Arduino Alive]
        ARDU_C -- Hayır --> ARDU_ERR[Arduino Dead]
        
        CPU_T --> MERGE_M
        CPU_L --> MERGE_M
        NET_T --> MERGE_M
        ARDU_OK --> MERGE_M
        ARDU_ERR --> MERGE_M
        MERGE_M[Tam Metrik Sözlüğü]
    end
    
    MERGE_M --> READ_EVENTS
    
    %% Olay Toplama
    subgraph READ_EVENTS_Q [Olay Kuyruğunu Oku]
        direction TB
        READ_EVENTS[API /event Kuyruğunu Çek] --> HAS_EVT{Kuyrukta Olay<br>Var mı?}
        HAS_EVT -- Evet --> POP_EVT(Olayları Metrik <br> Sözlüğüne Ekle)
        HAS_EVT -- Hayır --> KEEP_VAR(Sadece Metrikler)
        POP_EVT --> CONTEXT_DICT
        KEEP_VAR --> CONTEXT_DICT
    end
    
    CONTEXT_DICT --> EVAL_RULES
    
    %% Kural Değerlendirme Döngüsü
    subgraph RULE_EVALUATION [Kural Değerlendirme Motoru]
        direction TB
        EVAL_RULES[Tüm Kuralları Sırayla Kontrol Et]
        
        EVAL_RULES --> RULE_1{Kural 1: <br> if arduino == dead?}
        RULE_1 -- Evet (Öncelik 100) --> ACT_ERR[Kırmızı Renk, <br> breathe Animasyonu]
        
        RULE_1 -- Hayır --> RULE_2{Kural 2: <br> if cpu_temp > 85?}
        RULE_2 -- Evet (Öncelik 90) --> ACT_HOT[Turuncu Renk, <br> pulse Animasyonu]
        
        RULE_2 -- Hayır --> RULE_3{Kural 3: <br> if event == autonomy.greet?}
        RULE_3 -- Evet (Öncelik 80) --> ACT_GREET[Yeşil Renk, <br> wave Animasyonu]
        
        RULE_3 -- Hayır --> RULE_N{Kural N...}
        RULE_N -- Hiçbiri Uymadıysa --> ACT_DEF[Varsayılan Taban Animasyonu: BREATHE]
        
        ACT_ERR --> SEND_NEO
        ACT_HOT --> SEND_NEO
        ACT_GREET --> SEND_NEO
        ACT_DEF --> SEND_NEO
    end
    
    SEND_NEO(NeoHttpClient) --> HTTP_REQ([HTTP POST /neopixel/animate])
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    InteractionEngine ||--|| MetricsCollector : uses
    InteractionEngine ||--|| NeoHttpClient : calls
    EventAPI ||--o{"InteractionEngine : pushes_events
    
    MetricsCollector {
        get_cpu_temperature
                get_network_bytes
                get_cpu_load"}

    InteractionEngine {"list rules '(priority, condition, action)'
                tick"}

    NeoHttpClient {"string url 'localhost:8080/neopixel'
                play_animation_name__color"}
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **MetricsCollector Ölçümleri (Eşiğe Bağlı if'ler)**
   - **`if`** `psutil` kullanılarak CPU sıcaklığı ölçülür, RPi üzerindeki termal sensör okunur.
   - **Ağ Burst Tespiti:** **`if`** `(net_current - net_previous) > 5MB/s`: O anki tick için `network_burst = True` bayrağı açılır. Bu sayede robot yüksek veri indirirken gözler hareketlenir (wave/chase).
2. **Kural Değerlendirme Mekanizması (Rule Engine)**
   Sistem hardcode büyük if-else yığınlarını engellemek için `rules` listesi tutar. Her kural `priority` (öncelik, yüksekten düşüğe), `condition_func` (boolean dönen lambda) ve `action_dict` içerir.
   - **Döngü (Taranan Kurallar)** (örn `rules.sort(key=priority, reverse=True)`):
     - **`if`** `condition_func(context) == True`: Bu eylemi seç ve diğer alt öncelikli kuralları okumayı bırak (`break`).
     - Yüksek öncelikler: Sistem hataları (Arduino bağlantısı kopuk), kritik durumlar (CPU aşırı sıcak).
     - Orta öncelikler: Anlık dış olaylar (`autonomy.greet`, `vision.person_detected`).
     - Düşük öncelikler: Normal donanım etkinlikleri (CPU yükü hafif yüksek, Ağ indiriliyor).
     - **Hiçbir Kural Uymadı (Default/Else):** `BREATHE` animasyonunu ve `neutral` duygu paletini gönderir. Robot bekleme halinde yavaşça nefes alır.
3. **HTTP İsteğinde Statefulness Zekası**
   - **`if`** Seçilen eylem (animasyon + renk) bir önceki tick ile BİREBİR AYNI ise hiçbir HTTP çağrısı yapılmaz. Bu sayede sistemi boşuna ağ istekleriyle yormaz, sadece değişim anında bildirir.
