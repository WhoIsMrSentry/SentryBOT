# Skill: Gateway Bootstrap — Gateway'e Modül Kaydı

> Yeni bir modülü Gateway bootstrap sistemine kaydetme prosedürü.

## Dosyalar

### 1. `modules/gateway/services/bootstrap.py`'ye Ekleme

Mevcut bootstrap fonksiyonlarını incele, ardından yeni modül için ekle:

```python
def _include_{{MODULE_NAME}}(app, cfg: dict) -> dict:
    """{{MODULE_NAME}} modülünü başlat ve mount et."""
    try:
        from modules.{{MODULE_NAME}}.x{{SERVICE_NAME}}Service import _include_{{MODULE_NAME}} as mount
        return mount(app, cfg)
    except Exception as exc:
        logger.warning("{{MODULE_NAME}} module failed: %s", exc)
        return {}
```

Bootstrap sırası: `.sentrybot/agents/inter-module.md` dosyasındaki sıraya uy.

### 2. Gateway Config'e Ekleme

```yaml
# modules/gateway/config/config.yml
include:
  # ...mevcut modüller...
  {{MODULE_NAME}}: true
```

### 3. Bootstrap Ana Fonksiyonuna Çağrı Ekleme

`bootstrap(app, cfg)` fonksiyonunda `include.{{MODULE_NAME}}` kontrolü ekle:

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
- [ ] Bootstrap sırası korunuyor (bağımlılıklar önce yükleniyor)
- [ ] Modül başarısızsa warning loglanıyor (diğer modüller etkilenmiyor)
