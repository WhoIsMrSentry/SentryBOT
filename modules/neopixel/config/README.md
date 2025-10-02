# Neopixel Module Config

- server.host, server.port: FastAPI servis ayarları.
- hardware.device: SPI cihaz yolu (örn: /dev/spidev0.0).
- hardware.num_leds: LED sayısı.
- hardware.speed_khz: SPI hız (kHz).
- hardware.order: Renk sırası (GRB | RGB | BRG).
- defaults: Efekt varsayılan parametreleri.

Ortam değişkenleri ile override:
- NEO_CONFIG: Harici YAML yolu
- NEO_DEVICE, NEO_NUM_LEDS, NEO_SPEED_KHZ, NEO_ORDER
- NEO_HOST, NEO_PORT