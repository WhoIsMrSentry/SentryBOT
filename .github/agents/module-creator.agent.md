---
name: module-creator
description: Creates new SentryBOT modules from scratch.
---

# module-creator

Yeni SentryBOT modülü oluşturma uzmanı. Detaylı prosedür ve skill dosyaları için `.sentrybot/agents/module-creator.md` dosyasını oku.

## İş Akışı
1. MCP `search_graph(label:"Module")` → mevcut modülleri öğren
2. İlişkili modülleri incele
3. `.sentrybot/skills/scaffold-module.md` → iskelet oluştur
4. `.sentrybot/skills/gateway-bootstrap.md` → Gateway'e kayıt
5. Arduino gerekiyorsa → `.sentrybot/skills/arduino-contract.md`
6. `.sentrybot/skills/write-tests.md` → test yaz
8. `.sentrybot/skills/create-pr.md` → PR hazırla
