---
name: debug-module
description: SentryBOT: Debug Module â€” ModÃ¼l Debugging. Source: .sentrybot/skills/debug-module.md
---
# Skill: Debug Module â€” ModÃ¼l Debugging

> SentryBOT modÃ¼llerinde hata ayÄ±klama prosedÃ¼rÃ¼.

## HÄ±zlÄ± TeÅŸhis

### 1. ModÃ¼l SaÄŸlÄ±k KontrolÃ¼
```bash
# ModÃ¼l import edilebilir mi?
python -c "from modules.{{MODULE_NAME}} import *; print('OK')"

# Config yÃ¼klenebilir mi?
python -c "from modules.{{MODULE_NAME}}.config_loader import load_config; print(load_config())"

# Testler geÃ§iyor mu?
python -m pytest modules/{{MODULE_NAME}}/tests/ -v --maxfail=1
```

### 2. Log Analizi
```bash
# Son loglarÄ± incele
grep -i "error\|warning\|exception" logs/ --include="*.log" | grep {{MODULE_NAME}}
```

### 3. API SaÄŸlÄ±k KontrolÃ¼
```bash
# Gateway Ã¼zerinden durum kontrolÃ¼
curl http://localhost:8080/{{MODULE_NAME}}/status
curl http://localhost:8080/{{MODULE_NAME}}/healthz

# Genel sistem durumu
curl http://localhost:8080/status
```

### 4. Diagnostics ModÃ¼lÃ¼
```bash
# Otomatik sistem testi
curl -X POST http://localhost:8080/diagnostics/self_test
```

## YaygÄ±n Sorunlar

| Sorun | OlasÄ± Neden | Ã‡Ã¶zÃ¼m |
|-------|-------------|-------|
| Import hatasÄ± | Eksik baÄŸÄ±mlÄ±lÄ±k | `pip install -r modules/{{MODULE_NAME}}/requirements.txt` |
| Config hatasÄ± | YAML syntax | Config dosyasÄ±nÄ± YAML linter ile kontrol et |
| API 404 | Gateway'e kayÄ±tlÄ± deÄŸil | `gateway-bootstrap` skill'ini uygula |
| Arduino timeout | Seri baÄŸlantÄ± kopuk | `diagnostics/self_test` Ã§alÄ±ÅŸtÄ±r |
| ModÃ¼l Ã§Ã¶kmesi | Exception yakalanmamÄ±ÅŸ | try/except ekle, log incele |

## Ä°zole Test
```python
# ModÃ¼lÃ¼ izole Ã§alÄ±ÅŸtÄ±rma
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.{{MODULE_NAME}}.x{{SERVICE_NAME}}Service import {{SERVICE_NAME}}Service
svc = {{SERVICE_NAME}}Service(cfg={})
svc.start()
```

