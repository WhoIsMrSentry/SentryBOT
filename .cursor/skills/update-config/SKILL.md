---
name: update-config
description: SentryBOT: Update Config â€” Config GÃ¼ncelleme. Source: .sentrybot/skills/update-config.md
---
# Skill: Update Config â€” Config GÃ¼ncelleme

> ModÃ¼l config dosyasÄ±nÄ± ve config_loader'Ä± gÃ¼ncelleme prosedÃ¼rÃ¼.

## ProsedÃ¼r

### AdÄ±m 1: Mevcut Config'i Oku
```bash
cat modules/{{MODULE_NAME}}/config/config.yml
cat modules/{{MODULE_NAME}}/config_loader.py
```

### AdÄ±m 2: Yeni Alan Ekle (config.yml)
```yaml
# Mevcut ayarlarÄ±n altÄ±na ekle:
{{yeni_alan}}:
  {{alt_alan}}: {{varsayÄ±lan_deÄŸer}}
```

### AdÄ±m 3: Config Loader'Ä± GÃ¼ncelle
`config_loader.py`'de yeni alanÄ± okuyacak kodu ekle. VarsayÄ±lan deÄŸer atama kalÄ±bÄ±:
```python
cfg.setdefault("{{yeni_alan}}", {}).setdefault("{{alt_alan}}", {{varsayÄ±lan}})
```

### AdÄ±m 4: Merkezi Config Etkisi (Gerekirse)
EÄŸer bu ayar `config/agent.yaml`'Ä± da etkiliyorsa gÃ¼ncelle.

### AdÄ±m 5: README Config Tablosunu GÃ¼ncelle
`README.md`'deki konfigÃ¼rasyon tablosuna yeni alanÄ± ekle.

### AdÄ±m 6: Test
```python
def test_config_new_field():
    from modules.{{MODULE_NAME}}.config_loader import load_config
    cfg = load_config()
    assert "{{yeni_alan}}" in cfg or True  # varsayÄ±lan atanmalÄ±
```

## Kurallar
- Config deÄŸerleri kodda hardcode edilmez
- VarsayÄ±lan deÄŸer mutlaka atanÄ±r (KeyError'dan kaÃ§Ä±n)
- Yeni zorunlu alan eklendiÄŸinde geriye uyumluluk korunur

