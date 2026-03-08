# Mutagen Modülü Mimarisi

Mutagen modülü (`modules/mutagen`), geliştiricinin bilgisayarı (Windows/Mac) ile robot (Raspberry Pi/Jetson) arasında klasörleri canlı olarak eşzamanlayan `mutagen` aracını sarmalayan (wrap eden) komut satırı hizmetidir.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Sync Akışı
    START("Özel Geliştirici Scripti<br>(Örn: sync.bat)") --> CHK_MTG{"mutagen<br>kurulu mu?"}
    
    CHK_MTG -- "Hayır" --> ERR_MTG("Hata:<br>Mutagen CLI Bulunamadı")
    CHK_MTG -- "Evet" --> CREATE_SESSION("mutagen sync create<br>--name=sentrybot<br>./ -> pi@10.x.x.x:~/SentryBOT")
    
    CREATE_SESSION --> CHK_SESS{"Session Başarılı<br>Kuruldu mu?"}
    
    CHK_SESS -- "Hayır" --> ERR_SSH("Hata:<br>SSH Şifresi veya Host Yanlış")
    CHK_SESS -- "Evet" --> MON_SESS("mutagen sync monitor<br>sentrybot")
    
    %% Durum Yönetimi
    MON_SESS --> RUNNING("Sürekli Senkronizasyon<br>(İki yönlü + Ignore Listesi)")
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    DeveloperPC ||--|| RobotPi : rs_sync
    
    DeveloperPC {mutagen_daemon
        local_folder}
    
    RobotPi {ssh_server
        remote_folder}
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Ignore (Yok Sayılanlar) Mantığı**
   - Karşıya `.git`, `__pycache__`, `venv` ve SQLite veritabanları (Çünkü veritabanları rsync gibi canlı sync edilmeye çalışıldığında kilitlenir) gibi dosyaların kopyalanması **`if ignored`** kuralıyla engellenir. Bu konfigürasyon `mutagen.yml` içerisinde tutulur.
2. **Çarpışma (Conflict) Çözümü**
   - İki tarafta da aynı anda `config.yml` değiştirildiyse (Robot üzerinden web panelle değiştirildi, Bilgisayarda VS Code ile değiştirildi), Mutagen'in varsayılan kopyalama davranışı `resolve: remote-wins` (robotun bilgisini ezme) veya `local-wins` (kod yazan adamın ezmesi) kuralına göre önceliklendirilir.
