# Hardware Module

Raspberry Pi (veya üzerinde çalışılan SBC) donanımıyla ilgili düşük seviye bilgileri toplayan ve arayüzler sağlayan servis modülüdür. Sistem sağlığını (CPU, sıcaklık vb.) ve fiziksel pin/bus durumlarını sorgulamak için kullanılır.

## Özellikler
- **Sistem Anlık Görüntüsü (Snapshot):** CPU yükü, RAM kullanımı, disk durumu ve işlemci sıcaklığı gibi hayati sistem metriklerini okur.
- **I2C Tarama:** Sensör veya sürücü (ör: PCA9685, OLED) entegrasyonlarını debug etmek için I2C veriyolunu tarar ve bağlı cihazların adreslerini listeler.
- **GPIO Bilgisi:** Mevcut GPIO pin modunu (BCM, BOARD vb.) döner.

## API Uç Noktaları

Tüm uç noktalar varsayılan olarak `/hardware` prefix'i ile sunulur.

- `GET /hardware/healthz`
  Donanım modülünün ayakta olup olmadığını ve anlık sistem metriklerini döner.
- `GET /hardware/system`
  Raspberry Pi (SBC) sistem sıcaklığı, CPU ve bellek durumu snapshot'ını JSON formatında döner.
- `GET /hardware/i2c/scan`
  Yapılandırılmış I2C bus hattını tarar ve bağlı (yanıt veren) hex adreslerinin listesini döner. (Örn: `["0x3c", "0x40"]`)
- `GET /hardware/gpio/info`
  Tanımlanan GPIO yapılandırmasının özetini döner.

## Konfigürasyon (`config/config.yml`)
- `i2c.bus`: Taramanın yapılacağı I2C port numarası (genelde `1`).
- `gpio.mode`: GPIO numaralandırma modu (genelde `bcm`).
