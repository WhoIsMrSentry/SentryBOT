# Mutagen Sync Servisi

Mutagen CLI üzerinden dosya senkronizasyonu yönetir. CLI yoksa no-op döner.

API uçları:
- GET /mutagen/healthz
- GET /mutagen/status
- POST /mutagen/start
- POST /mutagen/stop
- POST /mutagen/rescan

Arduino OTA için: derlenmiş .hex dosyalarının bulunduğu klasörü ana makineden robota senkronlamak için bir pair tanımlayın ve `ota.watch_dir` ile eşleşmesini sağlayın.
