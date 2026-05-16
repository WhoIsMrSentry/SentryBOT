# Skill: Debug Module — Modül Debugging

> SentryBOT modüllerinde hata ayıklama prosedürü.

## Hızlı Teşhis

### 1. Modül Sağlık Kontrolü
```bash
# Modül import edilebilir mi?
python -c "from modules.{{MODULE_NAME}} import *; print('OK')"

# Config yüklenebilir mi?
python -c "from modules.{{MODULE_NAME}}.config_loader import load_config; print(load_config())"

# Testler geçiyor mu?
python -m pytest modules/{{MODULE_NAME}}/tests/ -v --maxfail=1
```

### 2. Log Analizi
```bash
# Son logları incele
grep -i "error\|warning\|exception" logs/ --include="*.log" | grep {{MODULE_NAME}}
```

### 3. API Sağlık Kontrolü
```bash
# Gateway üzerinden durum kontrolü
curl http://localhost:8080/{{MODULE_NAME}}/status
curl http://localhost:8080/{{MODULE_NAME}}/healthz

# Genel sistem durumu
curl http://localhost:8080/status
```

### 4. Diagnostics Modülü
```bash
# Otomatik sistem testi
curl -X POST http://localhost:8080/diagnostics/self_test
```

## Yaygın Sorunlar

| Sorun | Olası Neden | Çözüm |
|-------|-------------|-------|
| Import hatası | Eksik bağımlılık | `pip install -r modules/{{MODULE_NAME}}/requirements.txt` |
| Config hatası | YAML syntax | Config dosyasını YAML linter ile kontrol et |
| API 404 | Gateway'e kayıtlı değil | `gateway-bootstrap` skill'ini uygula |
| Arduino timeout | Seri bağlantı kopuk | `diagnostics/self_test` çalıştır |
| Modül çökmesi | Exception yakalanmamış | try/except ekle, log incele |

## İzole Test
```python
# Modülü izole çalıştırma
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.{{MODULE_NAME}}.x{{SERVICE_NAME}}Service import {{SERVICE_NAME}}Service
svc = {{SERVICE_NAME}}Service(cfg={})
svc.start()
```
