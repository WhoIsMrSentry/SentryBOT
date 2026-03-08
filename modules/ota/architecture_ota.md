# OTA (Over The Air) Modülü Mimarisi

OTA modülü (`modules/ota`), robotun kablosuz olarak uzak sunucudan (veya yerel olarak yüklenen bir ZIP dasyasından) yazılım güncellemelerini almasını, bunları ayrıştırmasını, dosyaları ezmesini ve güvenli bir restart sağlamasını kontrol eder.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% İstek Girişi
    START(POST /ota/update Dosya Icerir) --> CHK_ZIP{Zip/Tar<br>Geçerli mi?}
    
    %% Güvenlik ve Extract
    CHK_ZIP -- Hayır --> RET_ERR(Hata:<br>Dosya Bozuk veya Geçersiz)
    CHK_ZIP -- Evet --> EXTRACT_TMP(Geçici /tmp/sentry_upd<br>Klasörüne Aç)
    
    EXTRACT_TMP --> CHK_SIG{İmza/Checksum<br>Doğru mu?}
    CHK_SIG -- Hayır --> ABORT_UPD(Güvenlik İptali:<br>Geçersiz Paket)
    
    %% Kopyalama ve Yeniden Başlatma
    CHK_SIG -- Evet --> SHT_DOWN(Güvenli Mod<br>Tüm Motorları Sustur E Stop)

    SHT_DOWN --> CPY_FILES(Rsync veya Shutil ile<br>Kök Dizini Üzerine Yaz)

    CPY_FILES --> PIP_DEP{Yeni requirements_txt<br>var mı}
    PIP_DEP -- Evet --> RUN_PIP(Subprocess<br>pip install -r req txt)
    PIP_DEP -- Hayır --> TRIG_SYSTEMD(Systemd Servisini / PCyi<br>Yeniden Başlat Reboot)
    
    RUN_PIP --> TRIG_SYSTEMD
    TRIG_SYSTEMD --> EXIT_OK(Sistem Kapanıyor...)
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    OTAService ||--|| ArduinoSerial : sends_estop
    OTAService ||--|| LinuxOS : runs_shell_comands
    
    OTAService {verify_package
        apply_update
        system_reboot}
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Safety / E-Stop Mecburiyeti**
   - Robot çalışırken (örneğin yürüme komutları gidiyorken) programın beynini aniden yenilemeye çalışmak (veya reset atmak) robotun denge kaybetmesine, motorların kilitli kalıp yanmasına sebep olabilir.
   - Bu yüzden dosya değiştirme evresine (Overwrite) geçmeden hemen önce **ilk kural** Arduino'ya tüm servo torklarını boşa çıkarma komutu (`robot_command: home/zero/relax`) atamaktır.
2. **Paket Bütünlüğü (Checksum / Sig)**
   - Atılan ZIP dosyası ağ yüzünden yarım inmiş olabilir. `manifest.json` dosyasındaki hash ile arşivin gerçek hash'i karşılaştırılır. **`if`** eşleşmezse, yarı inmiş ve bozuk Python dosyalarının orijinal kodları ezmesini ve SentryBOT'u çöp etmesini engellemek için iptal (`Abort`) atılır.
