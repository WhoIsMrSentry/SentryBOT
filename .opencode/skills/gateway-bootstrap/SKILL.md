---
name: gateway-bootstrap
description: "Yeni modülü Gateway bootstrap sistemine kaydeder. bootstrap.py, config.yml ve include sıralaması."
---

# Gateway Bootstrap

## Adımlar
1. `modules/gateway/services/bootstrap.py`'ye `_include_<module>` fonksiyonu ekle
2. `modules/gateway/config/config.yml`'ye `include.<module>: true` ekle
3. Bootstrap sırasına uy (bağımlılıklar önce)

## Tam Prosedür
`.sentrybot/skills/gateway-bootstrap.md` dosyasını oku.
