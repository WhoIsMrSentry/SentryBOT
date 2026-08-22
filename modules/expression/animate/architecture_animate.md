# Animate Modülü Mimarisi

Animate modülü (`modules/animate`), robotun karmaşık gövde/kafa hareketlerini (animasyonlarını) zamanlanmış servo pozisyonlarına bölen ve bunları YAML dosyalarından okuyarak Arduino'ya aktaran sıralayıcı (sequencer) motordur.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Bir servo animasyonunun yüklenme, hız/tempo ayarı (speed) ve Arduino'ya iletilme adım (step) if/else mantığı:

```mermaid
flowchart TD
    %% Ana Giriş
    API_REQ([POST /animate/run]) --> PARSE_REQ(Parametreler: <br> name, speed, loop)
    
    PARSE_REQ --> CHK_NAME{"Animasyon<br>adı geçerli mi?"}
    
    %% Dosya Yükleme Kararları
    subgraph Loading Logic [YAML Yükleme ve Doğrulama]
        direction TB
        CHK_NAME -- Hayır --> RET_ERR([Hata: name gerekli])
        CHK_NAME -- Evet --> CHK_YAML(Dosyayı Oku: <br> animations/name.yml)
        
        CHK_YAML --> IS_EXIST{"Dosya Var mı?"}
        IS_EXIST -- Hayır --> RET_NF([Hata: Animasyon Bulunamadı])
        
        IS_EXIST -- Evet --> PARSE_YAML{"YAML formatı<br>doğru mu? (steps listesi)"}
        PARSE_YAML -- Hayır --> RET_INV([Hata: Geçersiz Format])
    end
    
    %% Oynatma Motoru (Sequencer)
    subgraph Engine Loop [Oynatma Motoru / Sequencer Döngüsü]
        direction TB
        PARSE_YAML -- Evet --> EXTRACT_STEPS(Tüm 'steps' listesini al)
        
        EXTRACT_STEPS --> LOOP_STEP[Döngü: Her step için]
        LOOP_STEP --> CALC_DUR(Hesapla: <br> duration = step.duration_ms / speed)
        
        CALC_DUR --> CHK_POSE{"Pose Verisi <br> Var mı?"}
        
        CHK_POSE -- Evet --> ACT_SRV(Arduino Serial:<br> 'set_pose' komutu gönder) --> ACT_WAIT(Bekle: 1 veya hesaplanan <br> süre kadar delay)
        CHK_POSE -- Hayır --> ACT_WAIT
        
        ACT_WAIT --> NEXT_STEP{"Bitti mi?"}
        NEXT_STEP -- Hayır --> LOOP_STEP
    end
    
    NEXT_STEP -- Evet --> CHK_LOOP{"Loop = True mu?"}
    CHK_LOOP -- Evet --> EXTRACT_STEPS
    CHK_LOOP -- Hayır --> RET_OK([ok: true])
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    AnimateService ||--o{ ArduinoSerial : sends_pose
    AnimateService ||--o{ YamlAnimations : reads

    AnimateService {
        string animation_name
        float speed
        bool loop
    }
    YamlAnimations {
        string file_path
        string steps_schema
    }
    ArduinoSerial {
        string pose_payload
        int duration_ms
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Güvenlik (Directory Traversal Koruması)**
   - API'ye dışarıdan `name=../../../etc/passwd` gibi zararlı şeyler gelebilir.
   - **`if`** `os.path.abspath` animasyon dizininin dışına taşıyorsa, dosya okumasını derhal reddeder. Sadece `modules/animate/animations/` altındaki `.yml` dosyalarını işler.
2. **Değişken Hız Katsayısı (Speed Multiplier)**
   - Autonomy beyni animasyon çağırırken robotun o anki duygu durumuna göre `speed` katsayısı gönderir (Örn mutluysa x1.2 hızlı, üzgünse x0.5 yavaş).
   - Motor, YAML'da yazan saf `duration_ms` değerini alır ve `(duration_ms / speed)` yaparak yeni bekleme süresini (timeout delay) hesaplar. Arduino'ya da hareketin ne kadar sürede tamamlanacağını (`duration`) bu yeni hesapla gönderir ki servo aniden seğirmesin, pürüzsüz ("smooth") gitsin.
3. **Loop ve Non-Blocking Çalışma**
   - Animasyonlar robotun beynini 10 saniye boyunca kilitlememelidir. Bu yüzden `run_animation` tetiklendiğinde Python arkada yeni bir `threading.Thread` başlatıp bu sleep/döngü işini ayrıştırır ve HTTP yanıtını anında döner `{"ok": True}`. Robot konuşurken veya başka iş yaparken servolar hareket etmeye devam eder.
