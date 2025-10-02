# Config Center

Modül config.yml dosyalarını görüntüleme, düzenleme ve panel ekleme (Blynk benzeri sürükle-bırak) arayüzü.

## API
- GET `/config/healthz`
- GET `/config/list`
- GET `/config/get?module=<name>`
- GET `/config/raw?module=<name>` (YAML dosyasını indirir)
- PUT `/config/set?module=<name>` (Body: text/plain YAML)
- POST `/config/register` (Body: { name, path })
- POST `/config/scan` (modüller altında config/config.yml dosyalarını otomatik bulur ve ekler)
- GET `/config/ui` (HTML liste)

## Özellikler
- Panelleri sürükle-bırak ile yeniden sırala (tarayıcıda saklanır)
- JSON/YAML görünüm toggle’ı
- Raw metin gösterimi
- Düzenle/Kaydet/Vazgeç ile YAML düzenleme (kaydetmeden önce YAML doğrulaması yapılır, dosya backup alınır)
- Otomatik kaydet (varsayılan açık) – düzenleme sırasında 600ms debounce ile dosyaya yazar
- Otomatik tarama – UI yüklenirken ve “Otomatik Tara” ile modülleri keşfeder
- Panel Ekle ile yeni YAML dosyası için panel tanımlama (config_center/config.yml içine best-effort persist)
