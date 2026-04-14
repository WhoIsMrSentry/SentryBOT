# NeoPixel Modülü Mimarisi

NeoPixel modülü (`modules/neopixel`), robotun göz veya gövde ışıklarını (WS2812/SK6812 LED şeritleri) kontrol eder. 20'den fazla yerleşik animasyon barındırır ve duygu durumlarına (joy, fear, neutral vb.) göre 23 farklı YAML paletinden renk eşleştirmesi yapar.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Bir animasyon veya renk değiştirme isteği geldiğinde, sistemin bunu donanıma (`pi5neo` veya `_SimStrip`) nasıl aktardığını gösteren diyagram:

```mermaid
flowchart TD
    %% Ana Giriş
    API_REQ([HTTP POST /animate]) --> PARSE_REQ(Gelen parametreler: <br> name, emotions, r, g, b, speed, loop)
    
    PARSE_REQ --> CHK_NAME{"Animasyon<br>Adı Var mı?"}
    
    %% Animasyon Yürütme Döngüsü
    subgraph Animation Pipeline [Animasyon Yürütme ve Renk Seçimi]
        direction TB
        
        CHK_NAME -- Hayır --> RET_ERR([Hata: name gerekli])
        CHK_NAME -- Evet --> CHK_COLOR{"r,g,b<br>verilmiş mi?"}
        
        %% Renk Belirleme Karar Ağacı
        CHK_COLOR -- Evet --> SET_RGB[r,g,b Kullan]
        CHK_COLOR -- Hayır --> CHK_EMOTION{"Emotions Listesi<br>Verilmiş mi?"}
        
        CHK_EMOTION -- Evet --> LOOP_EMO[Duyguları Sırayla Kontrol Et: <br> joy, curiosity...]
        LOOP_EMO --> FETCH_YML[EmotionStore'dan <br> emotion.yml Yükle]
        FETCH_YML --> CHK_YML{"Dosya ve Renk<br>Var mı?"}
        
        CHK_YML -- Evet --> RAND_PICK(Listeden Rastgele<br>Renk Seç) --> SET_RGB
        CHK_YML -- Hayır --> LOOP_EMO
        
        CHK_EMOTION -- Hayır --> SET_DEF[Varsayılan: Beyaz <br> r=255, g=255, b=255] --> SET_RGB
        
        %% Animasyon Tetikleme
        SET_RGB --> RUNNER_CALL(NeoRunner.animate)
        RUNNER_CALL --> DRIVER_CALL(NeoDriver.animate)
        
        %% Sürücü Karar Aşaması
        DRIVER_CALL --> CHK_HW{"Pi5Neo SPI<br>Erişilebilir mi?"}
        CHK_HW -- Evet --> HW_RUN(Donanım Hızlandırmalı<br>Sürücü - C modülü)
        CHK_HW -- Hayır --> SIM_RUN(_SimStrip - Geliştirici<br>Simülatörü Buffer'ı)
    end
    
    HW_RUN --> RET_OK([ok: true])
    SIM_RUN --> RET_OK
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    NeoRunner ||--|| NeoDriver : uses
    NeoRunner ||--|| EmotionStore : uses
    EmotionStore ||--o{ YamlFiles : reads

    NeoRunner {
        string current_animation
        string current_state
    }
    NeoDriver {
        int num_leds
        string color_order
    }
    EmotionStore {
        string emotion_key
        string palette_name
    }
    YamlFiles {
        string path
        string format
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Renk Seçimi (`resolve_colors`)**
   - Animasyon başlatılmadan önce renklerin belirlenmesi gerekir.
   - **`if`** `r,g,b` değerleri istekte API üzerinden açıkça verilmişse, doğrudan bu değerler kullanılır (Kullanıcı veya Autonomy belirli bir renk dayatmış demektir).
   - **`else if`** `emotions` listesi mevcutsa (örn: `["joy", "curiosity"]`), sistem `loader.py` üzerinden 23 YAML duygu paletine (`emotions/*.yml`) bakar. İlk bulduğu geçerli duygu dosyasından listelenmiş HEX veya RGB listesinden `random.choice()` ile rastgele bir renk seçer (böylece robot her mutlu olduğunda farklı, ama mutlu hissettiren sıcak renkler yanar).
   - **`else`**: Beyaz renk atanır `(255, 255, 255)`.
2. **Sürücü Seçimi (`NeoDriver.__init__`)**
   - Başlatma sırasında donanım sürücüsü seçilmek zorundadır.
   - **`try`**: `from pi5neo import Pi5Neo` yapmayı dener. Eğer kütüphane yüklüyse ve `/dev/spidev` portu açıksa donanım (C) tabanlı SPI sürücüsüne bağlanır.
   - **`except Exception`**: Windows, Mac veya SPI pinleri kapalı bir RPi üzerinde çalışıyorsa sistemin çökmemesi için `_SimStrip` isimli sahte (dummy) sınıfı yükler. Bu sınıf LED'lerin o anki RGB durumlarını sadece RAM'de tutar, LED'lere gerçekte bir data yollamaz ama diğer modüller hata almadan çalışmaya devam eder.
3. **Animasyon Durum Yönetimi**
   - Aynı animasyon üst üste istenirse donanımı gereksiz yormamak için **`if`** `current == requested`: görmezden gelinir.
   - `loop=True` ise donanım animasyonu kendi iç döngüsüne (sonsuz) alır; değilse belirli `iterations` kadar (örn: 3 kez nefes) yapar ve biter.
