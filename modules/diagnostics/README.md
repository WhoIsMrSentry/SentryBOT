# Diagnostics Module

SentryBOT'un alt modüllerinin sağlık durumunu kontrol eden ve toplu bir rapor üreten akıllı teşhis (diagnostics) servisidir. Boot sırasında veya çalışma anında sistemin genel stabilitesini ölçmek için kullanılır.

## Özellikler
- **Merkezi Kontrol:** Yapılandırılan modüllerin (kamera, donanım, ses vb.) HTTP `/healthz` veya `/status` uç noktalarına ping atarak yanıt sürelerini ve erişilebilirliklerini denetler.
- **Gecikme (Latency) Uyarıları:** Bir modül yavaş yanıt veriyorsa (varsayılan: >600ms) bunu raporda uyararak bildirir.
- **Self-Heal (Oto-Kurtarma):** Tekrarlayan hatalarda (ardışık hata sayısı aşıldığında) sorunlu servisi otomatik yeniden başlatma (eğer self-heal tanımlıysa) tetikleyebilir.

## API Uç Noktaları

Tüm uç noktalar Gateway üzerinden `/diagnostics` prefix'i ile sunulur.

- `GET /diagnostics/healthz`
  Teşhis servisinin kendisinin ayakta olup olmadığını döner.

- `POST /diagnostics/run`
  Yapılandırılmış (veya varsayılan) tüm modül sağlık kontrollerini asenkron (veya HTTP request'leriyle) paralel çalıştırır.
  **Dönen Yanıt:** Sistemdeki her bir modülün durumu (`ok`, `latency_ms`, `error`) ve genel sistem durumu (toplam başarılı/başarısız sayısı).

- `GET /diagnostics/report`
  Çalıştırılmış olan en son `/run` işleminin detaylı rapor sonucunu (cache'lenmiş haliyle) getirir. Ağır yük oluşturmadan önceki teşhis sonucunu okumak için kullanılır.

## Konfigürasyon (`config/config.yml`)
- `gateway_port`: Testlerin koşulacağı Gateway'in yerel portu (genelde 8080).
- `checks`: Hangi modüllerin, hangi HTTP metodu ve yolla kontrol edileceği. (Örn: `camera: { enabled: true, method: "GET", path: "/camera/healthz" }`)
- `thresholds`: Gecikme uyarı sınırı (`default_latency_warn_ms`) ve maksimum bekleme süresi (`default_timeout_ms`).
- `self_heal`: Arka arkaya kaç hatadan sonra otomatik kurtarma tetikleneceğinin kuralları.
