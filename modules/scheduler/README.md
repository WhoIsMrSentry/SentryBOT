# Scheduler

Basit async periyodik görev zamanlayıcı. HTTP ping işleri destekler.

Bu motor artık sadece config'te tanımlı işleri değil, çalışma anında eklenen işleri de yönetir.

## Ne İşe Yarar?
- Periyodik görevleri çalıştırır.
- Runtime'da yeni görev ekleyip kaldırabilir.
- Sonuçları kaydedip son çalıştırma bilgisini tutar.
- Farklı görev türlerini tek motor altında toplar.

## API
- GET `/scheduler/healthz`
- GET `/scheduler/jobs`
- POST `/scheduler/jobs/add`
- POST `/scheduler/jobs/remove/{job_id}`
- GET `/scheduler/jobs/results`
