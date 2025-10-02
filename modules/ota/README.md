# OTA (Arduino avrdude yükleme servisi)

- Derleme çıktısı (hex) `ota.watch_dir` içinde taranır; en son bulunan artefakt tek seferlik SHA256 ile versiyonlanır.
- Aynı isim ve hash tekrar yüklenmez.
- Yükleme `avrdude` ile yapılır; `ota.board` ve `ota.avrdude` ayarları üzerinden komut üretilir.
- API FastAPI router ile `/ota` altında sunulur: `healthz`, `scan_once`, `upload`, `versions`, `versions/clear`.

## Config
Bkz: `modules/ota/config/config.yml`

## Çalıştırma
Modül servis olarak çalıştırılabilir:

- `python -m modules.ota.xOTAService`

veya gateway ile mount edilerek kullanılabilir.
