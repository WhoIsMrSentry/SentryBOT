---
name: add-api-endpoint
description: "Mevcut SentryBOT modülüne yeni API endpoint ekler. Router, service, config ve test güncellemelerini kapsar."
---

# Add API Endpoint

Mevcut modüle yeni endpoint ekleme prosedürü.

## Adımlar
1. Mevcut `api/router.py` dosyasını incele (naming pattern)
2. Yeni route fonksiyonu ekle
3. Gerekirse `services/` altında service class oluştur
4. Config'e yeni parametreler ekle (gerekirse)
5. Test yaz
6. Architecture doc güncelle

## Tam Prosedür
`.sentrybot/skills/add-api-endpoint.md` dosyasını oku.
