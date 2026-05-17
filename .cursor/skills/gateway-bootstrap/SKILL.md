---
name: gateway-bootstrap
description: SentryBOT: Gateway Bootstrap â€” Gateway'e ModÃ¼l KaydÄ±. Source: .sentrybot/skills/gateway-bootstrap.md
---
# Skill: Gateway Bootstrap â€” Gateway'e ModÃ¼l KaydÄ±

> Yeni bir modÃ¼lÃ¼ Gateway bootstrap sistemine kaydetme prosedÃ¼rÃ¼.

## Dosyalar

### 1. `modules/gateway/services/bootstrap.py`'ye Ekleme

Mevcut bootstrap fonksiyonlarÄ±nÄ± incele, ardÄ±ndan yeni modÃ¼l iÃ§in ekle:

```python
def _include_{{MODULE_NAME}}(app, cfg: dict) -> dict:
    """{{MODULE_NAME}} modÃ¼lÃ¼nÃ¼ baÅŸlat ve mount et."""
    try:
        from modules.{{MODULE_NAME}}.x{{SERVICE_NAME}}Service import _include_{{MODULE_NAME}} as mount
        return mount(app, cfg)
    except Exception as exc:
        logger.warning("{{MODULE_NAME}} module failed: %s", exc)
        return {}
```

Bootstrap sÄ±rasÄ±: `.sentrybot/agents/inter-module.md` dosyasÄ±ndaki sÄ±raya uy.

### 2. Gateway Config'e Ekleme

```yaml
# modules/gateway/config/config.yml
include:
  # ...mevcut modÃ¼ller...
  {{MODULE_NAME}}: true
```

### 3. Bootstrap Ana Fonksiyonuna Ã‡aÄŸrÄ± Ekleme

`bootstrap(app, cfg)` fonksiyonunda `include.{{MODULE_NAME}}` kontrolÃ¼ ekle:

```python
if inc.get("{{MODULE_NAME}}", False):
    try:
        result = _include_{{MODULE_NAME}}(app, cfg)
        started.update(result)
    except Exception as exc:
        logger.warning("{{MODULE_NAME}} failed: %s", exc)
```

## Kontrol Listesi
- [ ] `bootstrap.py`'ye `_include_{{MODULE_NAME}}` fonksiyonu eklendi
- [ ] `config.yml`'ye `include.{{MODULE_NAME}}: true` eklendi
- [ ] Bootstrap sÄ±rasÄ± korunuyor (baÄŸÄ±mlÄ±lÄ±klar Ã¶nce yÃ¼kleniyor)
- [ ] ModÃ¼l baÅŸarÄ±sÄ±zsa warning loglanÄ±yor (diÄŸer modÃ¼ller etkilenmiyor)

