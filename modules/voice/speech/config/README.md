# Speech Config

Bu dosya yalnızca konuşma modülünün ayarlarını içerir.

- server.host / server.port: FastAPI servis adresi
- audio.*: ALSA/I2S cihaz ve örnekleme ayarları
- recognition.*: Vosk modeli ve seçenekleri

Varsayılanlar bu dizindeki `config.yml` içinde bulunur; servis başlatılırken harici bir yol ile override edilebilir.
