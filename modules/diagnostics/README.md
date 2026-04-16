# Diagnostics Module

Boot self-check ve modül sağlık taraması. Gateway üzerinden yerel endpointleri çağırır.

Bu modül yalnızca servislerin yanıt verip vermediğine bakmaz; yanıt süresi, tekrar eden hata ve iyileştirme ihtiyacını da değerlendirir.

## Ne İşe Yarar?
- Endpoint gecikmelerini eşiklerle karşılaştırır.
- Aynı hatanın art arda tekrarını sayar.
- Raporları kısa süreli cache ile yeniden kullanır.
- Self-heal açıksa notifier veya onarım callback’leri tetikleyebilir.

## API
- GET `/diagnostics/healthz`
- POST `/diagnostics/run`
- GET `/diagnostics/report`
