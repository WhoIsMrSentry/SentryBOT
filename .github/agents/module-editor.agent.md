---
name: module-editor
description: Edits existing SentryBOT modules — adds endpoints, services, config changes, bug fixes, and refactoring while maintaining backward compatibility.
argument-hint: "a module modification task (e.g., 'add volume endpoint to speak module' or 'fix VLM tracker crash')"
---

# Module Editor Agent

Mevcut modül düzenleme uzmanı. Detaylı prosedür için `.sentrybot/agents/module-editor.md` dosyasını oku.

## İş Akışı
1. Hedef modülün `architecture_*.md` ve `config.yml` dosyalarını oku
2. Değişiklik türünü belirle (endpoint/service/config/fix/refactor)
3. Uygun skill'i seç ve uygula
4. Testleri güncelle → `.sentrybot/skills/write-tests.md`
5. Architecture doc güncelle → `.sentrybot/skills/write-architecture-doc.md`
6. PR hazırla → `.sentrybot/skills/create-pr.md`
