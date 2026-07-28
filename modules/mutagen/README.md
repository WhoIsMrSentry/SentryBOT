# Mutagen Module

Mutagen CLI tabanlı dosya senkronizasyon altyapısını robot üzerinden yönetmeye yarayan arayüz modülüdür. Özellikle geliştirici cihazı (PC/Mac) ile robot (Raspberry Pi) arasındaki kodların iki yönlü, gerçek zamanlı ve hızlı eşitlenmesinde OTA sürecine destek olur.

## Özellikler
- **Uzaktan Yönetim:** Geliştiricinin SSH veya ekstra terminal açmasına gerek kalmadan, Gateway üzerinden senkronizasyonu başlatıp durdurmasını sağlar.
- **Durum Gözlemi:** Arka planda çalışan Mutagen oturumunun durumunu veya hata loglarını HTTP ile sunar.
- **Zorunlu Tarama:** Dosya değişikliklerini beklemeden senkronizasyonu manuel tetikleme (`rescan`).

## API Uç Noktaları

Tüm uç noktalar Gateway altında `/mutagen` prefix'i ile erişilebilir.

- `GET /mutagen/healthz`
  Servis durumunu kontrol eder.
- `GET /mutagen/status`
  Arka planda çalışan mutagen oturumunun güncel bilgisini (bağlantı durumu, bekleyen dosya var mı vb.) JSON olarak döner.
- `POST /mutagen/start`
  Mutagen daemon ve senkronizasyon oturumunu başlatır (konfigürasyondaki alpha/beta yollarına göre).
- `POST /mutagen/stop`
  Senkronizasyon oturumunu kapatır ve izlemeyi durdurur.
- `POST /mutagen/rescan`
  Senkronizasyon klasörlerinin tam taranmasını (full rescan) zorlar. Olası inatçı eşitleme sorunlarını çözer.

## Konfigürasyon (`config/config.yml`)
- `mutagen.session_name`: Oturuma verilecek isim.
- `mutagen.alpha`: Kaynak cihazın (veya Pi'nin kendisinin) senkronize edilecek dizin yolu.
- `mutagen.beta`: Hedef dizin yolu.
- Diğer Mutagen CLI parametreleri (ignore list vb.).
