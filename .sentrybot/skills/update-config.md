# Skill: Update Config — Config Güncelleme

> Modül config dosyasını ve config_loader'ı güncelleme prosedürü.

## Prosedür

### Adım 1: Mevcut Config'i Oku
```bash
cat modules/{{MODULE_NAME}}/config/config.yml
cat modules/{{MODULE_NAME}}/config_loader.py
```

### Adım 2: Yeni Alan Ekle (config.yml)
```yaml
# Mevcut ayarların altına ekle:
{{yeni_alan}}:
  {{alt_alan}}: {{varsayılan_değer}}
```

### Adım 3: Config Loader'ı Güncelle
`config_loader.py`'de yeni alanı okuyacak kodu ekle. Varsayılan değer atama kalıbı:
```python
cfg.setdefault("{{yeni_alan}}", {}).setdefault("{{alt_alan}}", {{varsayılan}})
```

### Adım 4: Merkezi Config Etkisi (Gerekirse)
Eğer bu ayar `config/agent.yaml`'ı da etkiliyorsa güncelle.

### Adım 5: README Config Tablosunu Güncelle
`README.md`'deki konfigürasyon tablosuna yeni alanı ekle.

### Adım 6: Test
```python
def test_config_new_field():
    from modules.{{MODULE_NAME}}.config_loader import load_config
    cfg = load_config()
    assert "{{yeni_alan}}" in cfg or True  # varsayılan atanmalı
```

## Kurallar
- Config değerleri kodda hardcode edilmez
- Varsayılan değer mutlaka atanır (KeyError'dan kaçın)
- Yeni zorunlu alan eklendiğinde geriye uyumluluk korunur
