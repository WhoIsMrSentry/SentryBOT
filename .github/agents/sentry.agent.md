---
name: sentrybot
description: SentryBOT modular robot platform AI agent. Routes to .sentrybot/ for all workflows, skills, and conventions.
---

# SentryBOT Agent

Bu agent, SentryBOT deposundaki tüm iş akışları için yönlendirici görevi görür.

## Tek Merkez: `.sentrybot/`

Tüm agent, skill, context ve template dosyaları `.sentrybot/` dizininde toplanmıştır.

### İş Akışı Yöneticileri (Agents)
- **Yeni Modül Oluşturma**: `.sentrybot/agents/module-creator.md`
- **Mevcut Modül Düzenleme**: `.sentrybot/agents/module-editor.md`
- **GitHub İşlemleri**: `.sentrybot/agents/github-ops.md`
- **Modüller Arası Etkileşim**: `.sentrybot/agents/inter-module.md`
- **Kod İnceleme**: `.sentrybot/agents/code-reviewer.md`

### Prosedürler (Skills)
Tüm skill listesi: `.sentrybot/skills/` (12 adım adım prosedür)

### Context
- **Modül Listesi**: MCP `search_graph(label:"Module")` veya `get_architecture()`
- **API Yüzeyi**: MCP `search_graph(label:"Route")`
- **Mimari**: `.sentrybot/context/architecture-summary.md`
- **Kurallar**: `.sentrybot/context/conventions.md`

### Kurallar
1. **DryCode** — Tekrar yok, sade, net
2. **Arduino kontratı** — `contract.py` builder zorunlu
3. **Config** — Hardcode yasak, YAML'den oku
4. **Test** — Her modülde smoke test zorunlu
5. **Modül yapısı** — `x<Name>Service.py` + `config_loader.py` + `api/router.py`
