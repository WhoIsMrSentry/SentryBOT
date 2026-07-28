# State Manager Module

SentryBOT'un paylaşılan (global) bellek ve durum (state) yönetim merkezidir. Farklı modüllerin (örneğin otonomi, kamera, hareket) birbirleriyle durum paylaşabilmesini ve robotun anlık modunu, duygu durumlarını, operasyonel safhalarını merkezi bir noktadan sorgulayıp güncelleyebilmelerini sağlar.

## Özellikler
- **Kalıcı Durum (Persistence):** Robot yeniden başladığında önceki operasyonel durumunu veya duygularını hatırlayabilmesi için (json veya sqlite backend kullanılarak) verileri diske yazar.
- **Duygu ve Operasyonel Mod Yönetimi:** Robotun o anki duygularını (emotions: `joy`, `sadness` vb.) ve operasyonel modunu (`idle`, `busy`, `sleeping`) yönetmek için özel uç noktalar sunar. 

## API Uç Noktaları

Uç noktalar Gateway altında `/state` prefix'i ile sunulur.

- `GET /state/healthz`
  Servis sağlık durumu.

- `GET /state/get`
  Sistemde kayıtlı olan tüm global durum (state) nesnesini JSON olarak döner. İçerisinde `operational` (string) ve `emotions` (array) gibi standart anahtarlar bulunur.

- `POST /state/set`
  Genel bir key-value güncellemesi yapar. Verilen JSON objesindeki anahtarları mevcut durum (state) üzerine yazar.
  **Gövde (JSON):** Herhangi bir `{ "anahtar": "deger" }` çifti.

- `POST /state/set/operational`
  Robotun çalışma modunu ayarlar.
  **Gövde (JSON):** `{ "value": "busy" }` veya `"idle"`, `"sleep"`.

- `POST /state/set/emotions`
  Robotun anlık duygularını ayarlar.
  **Gövde (JSON):** `{ "values": ["joy", "curiosity"] }` veya tek bir string `{ "values": "sadness" }`.

## Konfigürasyon (`config/config.yml`)
- Backend tipi (`json`, `memory`, `sqlite`) ve dosya yolları bu modülün konfigürasyonu altından yönetilir.
