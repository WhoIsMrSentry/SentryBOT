---
name: scaffold-module
description: "SentryBOT deposuna sıfırdan yeni modül iskeleti oluşturur. 10 dosyalı standart yapı: xService, config, router, tests, docs."
---

# Scaffold Module

SentryBOT modül yapı kurallarına uygun iskelet oluştur.

## Oluşturulacak Dosyalar
```
modules/<module_name>/
├── __init__.py
├── x<ModuleName>Service.py
├── config_loader.py
├── config/config.yml
├── api/__init__.py
├── api/router.py
├── services/__init__.py
├── tests/test_smoke.py
├── architecture_<name>.md
└── README.md
```

## Tam Şablonlar
`.sentrybot/skills/scaffold-module.md` dosyasında her dosyanın tam kod şablonu mevcut.

## Kurallar
- Config değerleri hardcode edilmez
- Her modül hem kütüphane hem servis olarak çalışabilmeli
- Smoke test zorunlu
