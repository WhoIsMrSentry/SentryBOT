# Scheduler Modülü Mimarisi

Scheduler modülü (`modules/scheduler`), robotun arka planda her 1 dakika, saat başı veya gece 3'te yapması gereken zamanlanmış görevleri (Cron mantığı) yürüten ve yöneten servistir.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Zamanlayıcı Döngüsü
    START(Background Thread Her saniye uyanir) --> GET_TIME(Şu Anki Saati Al)
    
    GET_TIME --> CHK_CRON{Kayıtlı Görevlerin<br>Zamanı Geldi mi?}
    
    CHK_CRON -- Hayır --> SLEEP(sleep 1) --> START
    CHK_CRON -- Evet --> FORK_TASK(İlgili Fonksiyonu<br>Ayrı Threadde Başlat)
    
    %% Örnek Görevler
    FORK_TASK --> TASK_1(Gece 03:00<br>Sohbet Loglarını Temizle)
    FORK_TASK --> TASK_2(Sabah 08:00<br>Otonomi Uyanma Titremesi)
    FORK_TASK --> TASK_3(Her 30dk<br>Battery Metrik Logla)
    
    TASK_1 --> SLEEP
    TASK_2 --> SLEEP
    TASK_3 --> SLEEP
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    SchedulerService ||--o{ AllModules : executes_callbacks

    SchedulerService {
        string cron_expr
        string task_id
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Zamanlanmış Olarak Görev Tetikleme (Cron Parser)**
   - Modül içinde Python `schedule` kütüphanesi sarmalanır.
   - **`if`** bir komut/algoritma bloklanıyorsa (Örneğin "Logları buluta yedekleme" işlemi 5 dakika sürüyorsa), ana scheduler thread'inin donup diğer zamanlanmış görevleri (Örn: Alarm çalma) kaçırmaması için **her çalışan fonksiyon** yeni bir `threading.Thread(target=func).start()` bloğu içine alınır. Bu "Non-blocking" mimaridir.
