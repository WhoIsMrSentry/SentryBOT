---
name: debug-module
description: "SentryBOT modüllerinde hata ayıklama. Sağlık kontrolü, log analizi, yaygın sorunlar ve izole test."
---

# Debug Module

## Hızlı Teşhis
```bash
# Import kontrolü
python -c "from modules.<modül> import *; print('OK')"

# Config kontrolü
python -c "from modules.<modül>.config_loader import load_config; print(load_config())"

# Test
python -m pytest modules/<modül>/tests/ -v --maxfail=1

# API sağlık
curl http://localhost:8080/<modül>/status
```

## Tam Prosedür
`.sentrybot/skills/debug-module.md` dosyasını oku.
