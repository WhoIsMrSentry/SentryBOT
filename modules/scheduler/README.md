# Scheduler Module

SentryBOT içindeki görevlerin zamanlanması, periyodik işlerin (cron benzeri) arka planda yürütülmesi ve HTTP ping görevlerinin yönetilmesini sağlayan görev yöneticisi (task scheduler) servisidir.

## Özellikler
- **Dinamik Görev Yönetimi:** Yalnızca başlatma sırasında `config.yml` üzerinden değil, çalışma anında (runtime) HTTP API kullanılarak da periyodik görevler eklenebilir, silinebilir veya değiştirilebilir.
- **HTTP Ping Görevleri:** Özellikle harici servislere veya robotun kendi sensör arayüzlerine düzenli "keep-alive" veya "poll" (yoklama) isteği atabilir.
- **Sonuç Takibi:** Çalıştırılan görevlerin son çalışma durumlarını ve aldıkları yanıtları saklar.

## API Uç Noktaları

Uç noktalar Gateway altında `/scheduler` prefix'i ile tanımlıdır.

- `GET /scheduler/healthz`
  Servis sağlık kontrolü.
  
- `GET /scheduler/jobs`
  Şu anda kayıtlı ve zamanlanmış olan tüm görevlerin (jobs) listesini döner.

- `POST /scheduler/jobs`
  Yeni bir görev ekler veya var olanı günceller.
  **Gövde (JSON):** Görev tanımlarını içerir (interval_s, url, method vb.).
  
- `DELETE /scheduler/jobs/{job_id}`
  ID'si belirtilen zamanlanmış görevi sistemden siler.

- `GET /scheduler/results`
  Görevlerin son çalıştırılma sonuçlarını (başarı/hata durumları, dönen HTTP kodları) listeler.

- `POST /scheduler/run_once/{job_id}`
  Periyodik süreyi beklemeden ilgili görevi anında bir kereliğine manuel tetikler (asenkron).

## Konfigürasyon (`config/config.yml`)
- Başlangıçta yüklenecek varsayılan görevler listesi (jobs) buradan tanımlanabilir.
