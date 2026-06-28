---
name: inter-module
description: Manages cross-module interactions.
---

# inter-module

Modüller arası etkileşim uzmanı. Detaylı prosedür için `.sentrybot/agents/inter-module.md` dosyasını oku.

## İş Akışı
1. MCP `search_graph(label:"Route")` → mevcut endpoint'leri öğren
2. MCP `search_graph(label:"Module")` → bağımlılıkları incele
3. İletişim türünü seç (HTTP/Arduino/State/Event)
4. `.sentrybot/skills/module-dependency-map.md` → bağımlılık analizi
