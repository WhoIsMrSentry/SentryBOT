# Logwrapper Config

Aşağıdaki anahtarlar `config.yml` içinde tanımlıdır:

- enable_console: bool – Konsola log yazımı
- console_level: str – Konsol seviye eşiği (DEBUG/INFO/...)
- enable_file: bool – Dosyaya log yazımı
- file_path: str – Log dosya yolu
- rotate_bytes: int – Rotasyon boyutu (bytes)
- backup_count: int – Yedek dosya sayısı
- json_format: bool – JSON formatta çıktı (harici bağımlılık yok)
- buffer_size: int – Bellek içi halka buffer kapasitesi
- capture_warnings: bool – warnings -> logging
- module_levels: dict – Örn: {"uvicorn": "WARNING"}

Override önceliği: overrides dict > ortam değişkenleri (LOG_LEVEL, LOG_FILE) > YAML > varsayılanlar.
