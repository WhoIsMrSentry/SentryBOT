---
name: module-dependency-map
description: SentryBOT: Module Dependency Map â€” ModÃ¼l BaÄŸÄ±mlÄ±lÄ±k Haritalama. Source: .sentrybot/skills/module-dependency-map.md
---
# Skill: Module Dependency Map â€” ModÃ¼l BaÄŸÄ±mlÄ±lÄ±k Haritalama

> ModÃ¼ller arasÄ± baÄŸÄ±mlÄ±lÄ±klarÄ± analiz etme ve haritalama prosedÃ¼rÃ¼.

## Analiz ProsedÃ¼rÃ¼

### AdÄ±m 1: Import TaramasÄ±
```bash
# ModÃ¼lÃ¼n hangi diÄŸer modÃ¼lleri import ettiÄŸini bul
grep -r "from modules\." modules/{{MODULE_NAME}}/ --include="*.py" | grep -v __pycache__
grep -r "import modules\." modules/{{MODULE_NAME}}/ --include="*.py" | grep -v __pycache__
```

### AdÄ±m 2: HTTP Ã‡aÄŸrÄ± TaramasÄ±
```bash
# ModÃ¼lÃ¼n hangi endpoint'leri Ã§aÄŸÄ±rdÄ±ÄŸÄ±nÄ± bul
grep -rn "localhost:8080\|/arduino/\|/speak/\|/neopixel/\|/ollama/\|/vlm/\|/state/" \
  modules/{{MODULE_NAME}}/ --include="*.py" | grep -v __pycache__
```

### AdÄ±m 3: Config BaÄŸÄ±mlÄ±lÄ±k TaramasÄ±
```bash
# Config'de referans verilen URL'leri bul
grep -n "endpoint\|url\|host\|port" modules/{{MODULE_NAME}}/config/config.yml
```

### AdÄ±m 4: BaÄŸÄ±mlÄ±lÄ±k DiyagramÄ± OluÅŸtur

```mermaid
graph LR
    {{MODULE_NAME}} --> |HTTP| modÃ¼l_a
    {{MODULE_NAME}} --> |Serial| modÃ¼l_b
    modÃ¼l_c --> |HTTP| {{MODULE_NAME}}
```

## BaÄŸÄ±mlÄ±lÄ±k TÃ¼rleri

| TÃ¼r | AÃ§Ä±klama | Ã–rnek |
|-----|----------|-------|
| **DoÄŸrudan** | Import ile | `from modules.x import Y` |
| **HTTP** | API Ã§aÄŸrÄ±sÄ± ile | `POST /speak/say` |
| **Serial** | Arduino kontratÄ± ile | `contract.build_set_servo()` |
| **Config** | Config referansÄ± ile | `endpoint: http://localhost:8080/x` |
| **Event** | Olay bildirimi ile | `POST /interactions/event` |

## Ã‡Ä±ktÄ± FormatÄ±
BaÄŸÄ±mlÄ±lÄ±k haritasÄ± `.sentrybot/context/module-registry.md`'deki "Kilit BaÄŸÄ±mlÄ±lÄ±klar" sÃ¼tununa yansÄ±tÄ±lÄ±r.

