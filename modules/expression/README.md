# Expression Module

SentryBOT'un semantik ifade motoru. Sistemde meydana gelen olayları ve soyut komutları (örneğin: `status: busy` veya `event: recognized_face`) algılayıp, bunu fiziksel ve görsel bir ifadeye (animasyon, renk, oled göz durumu, ses efekti) dönüştürür.

## Ne İşe Yarar?
- **Olay Çevirisi (Event Translation):** Etkileşim olaylarını ve donanım tetikleyicilerini mantıksal bir 'ifade' durumuna eşler.
- **Dinamik Tepkiler:** Sabit kodlanmış animasyonlar yerine bağlama duyarlı semantik ifadeler (`SemanticExpressionEngine`) üretir.
- **Görsel/İşitsel Senkronizasyon:** OLED ekran yüzü (`oled_faces`), NeoPixel ışıkları (`neopixel`) ve diğer donanım bileşenlerini aynı duygu veya durumu yansıtacak şekilde birbiriyle senkronize eder.

## API Uç Noktaları
- `GET /expression/healthz` - Servis durumunu döndürür.
- `GET /expression/state` - Mevcut aktif ifade durumunu (`get_state`) getirir.
- `GET /expression/status` - Motorun anlık durumu ve aktif kuralların özeti.
- `POST /expression/apply` - Manuel bir ifade tetikler. Parametreler: `payload` (ifade verisi), `source` (kaynak belirtimi), `reason` (tetiklenme sebebi).
- `POST /expression/event` - Belirli bir sistem olayını ifade motoruna bildirir (`event_type`, opsiyonel `data`).

## Kullanım
Modül, `gateway` üzerinden veya diğer modüller tarafından `on_interaction_event` çağrılarıyla kullanılabilir. İfade motoru, `config.yml` dosyasında tanımlanan kurallar setine göre (SemanticExpressionEngine) girdileri yorumlar ve robotun donanımlarına (OLED, LED) gerekli komutları dağıtır.

## Konfigürasyon (`config/config.yml`)
İfade kuralları, olay türleri ve bu olaylara verilecek tepki ağırlıkları modülün yapılandırma dosyasında belirtilir. Bu sayede kod değiştirmeden robotun bir olaya (örneğin bir kişinin görülmesi) nasıl tepki vereceği (ışık rengi, ekran animasyonu) özelleştirilebilir.
