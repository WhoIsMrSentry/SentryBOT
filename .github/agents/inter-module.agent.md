---
name: inter-module
description: Manages cross-module communication, API integration, event systems, and data flow between SentryBOT modules.
argument-hint: "a cross-module task (e.g., 'connect new sensor to autonomy brain' or 'add event trigger from wakeword to neopixel')"
---

# Inter-Module Agent

Modüller arası etkileşim uzmanı. Detaylı prosedür için `.sentrybot/agents/inter-module.md` dosyasını oku.

## İş Akışı
1. `.sentrybot/context/api-surface.md` → mevcut endpoint'leri öğren
2. `.sentrybot/context/module-registry.md` → bağımlılıkları incele
3. İletişim türünü seç (HTTP/Arduino/State/Event)
4. `.sentrybot/skills/module-dependency-map.md` → bağımlılık analizi
