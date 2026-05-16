# Skill: Write Architecture Doc — Mimari Dokümantasyon Yazma

> `architecture_<module_name>.md` dosyası yazma formatı ve kuralları.

## Şablon

```markdown
# <ModuleName> — Mimari Dokümantasyon

## Genel Bakış
Modülün tek cümlelik açıklaması ve görevi.

## Modül Yapısı
\```
modules/<module_name>/
├── __init__.py
├── x<Name>Service.py
├── config_loader.py
├── config/
│   └── config.yml
├── api/
│   └── router.py
├── services/
│   └── <servis_dosyaları>.py
├── tests/
│   └── test_smoke.py
├── architecture_<module_name>.md
└── README.md
\```

## Veri Akışı
\```mermaid
flowchart TD
    A[Giriş] --> B{Karar noktası}
    B -- Koşul 1 --> C[İşlem 1]
    B -- Koşul 2 --> D[İşlem 2]
    C --> E[Çıkış]
    D --> E
\```

## Modüller Arası Etkileşim
| Modül | Bu Modül ile İlişkisi |
|---|---|
| `gateway` | Bootstrap ile mount eder |
| `<diğer>` | <ilişki açıklaması> |

## Tasarım Kararları
### Neden X yerine Y?
Kararın gerekçesi, trade-off'lar.

### Genişletilebilirlik
Modülün nasıl genişletilebileceği veya değiştirilebileceği.
```

## Kurallar
- Mermaid diyagramı zorunlu (en az bir flowchart)
- Modüller arası etkileşim tablosu zorunlu
- En az bir tasarım kararı belgelenecek
- Türkçe yazılabilir (mevcut convention)
