---
name: write-architecture-doc
description: SentryBOT: Write Architecture Doc â€” Mimari DokÃ¼mantasyon Yazma. Source: .sentrybot/skills/write-architecture-doc.md
---
# Skill: Write Architecture Doc â€” Mimari DokÃ¼mantasyon Yazma

> `architecture_<module_name>.md` dosyasÄ± yazma formatÄ± ve kurallarÄ±.

## Åablon

```markdown
# <ModuleName> â€” Mimari DokÃ¼mantasyon

## Genel BakÄ±ÅŸ
ModÃ¼lÃ¼n tek cÃ¼mlelik aÃ§Ä±klamasÄ± ve gÃ¶revi.

## ModÃ¼l YapÄ±sÄ±
\```
modules/<module_name>/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ x<Name>Service.py
â”œâ”€â”€ config_loader.py
â”œâ”€â”€ config/
â”‚   â””â”€â”€ config.yml
â”œâ”€â”€ api/
â”‚   â””â”€â”€ router.py
â”œâ”€â”€ services/
â”‚   â””â”€â”€ <servis_dosyalarÄ±>.py
â”œâ”€â”€ tests/
â”‚   â””â”€â”€ test_smoke.py
â”œâ”€â”€ architecture_<module_name>.md
â””â”€â”€ README.md
\```

## Veri AkÄ±ÅŸÄ±
\```mermaid
flowchart TD
    A[GiriÅŸ] --> B{Karar noktasÄ±}
    B -- KoÅŸul 1 --> C[Ä°ÅŸlem 1]
    B -- KoÅŸul 2 --> D[Ä°ÅŸlem 2]
    C --> E[Ã‡Ä±kÄ±ÅŸ]
    D --> E
\```

## ModÃ¼ller ArasÄ± EtkileÅŸim
| ModÃ¼l | Bu ModÃ¼l ile Ä°liÅŸkisi |
|---|---|
| `gateway` | Bootstrap ile mount eder |
| `<diÄŸer>` | <iliÅŸki aÃ§Ä±klamasÄ±> |

## TasarÄ±m KararlarÄ±
### Neden X yerine Y?
KararÄ±n gerekÃ§esi, trade-off'lar.

### GeniÅŸletilebilirlik
ModÃ¼lÃ¼n nasÄ±l geniÅŸletilebileceÄŸi veya deÄŸiÅŸtirilebileceÄŸi.
```

## Kurallar
- Mermaid diyagramÄ± zorunlu (en az bir flowchart)
- ModÃ¼ller arasÄ± etkileÅŸim tablosu zorunlu
- En az bir tasarÄ±m kararÄ± belgelenecek
- TÃ¼rkÃ§e yazÄ±labilir (mevcut convention)

