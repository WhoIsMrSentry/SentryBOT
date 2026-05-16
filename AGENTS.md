# AGENTS.md — AI Agent Keşif Dosyası

Bu dosya, SentryBOT deposuyla çalışan tüm AI kodlama asistanlarının otomatik keşfedeceği rehber dosyasıdır.

## 📁 TEK MERKEZ: `.sentrybot/`

Tüm detaylı agent, skill, context ve template dosyaları **tek dizinde** toplanmıştır:

```
.sentrybot/
├── agents/              # 5 iş akışı yöneticisi
│   ├── module-creator.md
│   ├── module-editor.md
│   ├── github-ops.md
│   ├── inter-module.md
│   └── code-reviewer.md
├── skills/              # 12 adım adım prosedür
│   ├── scaffold-module.md
│   ├── add-api-endpoint.md
│   ├── add-service-class.md
│   ├── update-config.md
│   ├── write-tests.md
│   ├── write-architecture-doc.md
│   ├── arduino-contract.md
│   ├── gateway-bootstrap.md
│   ├── create-pr.md
│   ├── create-issue.md
│   ├── module-dependency-map.md
│   └── debug-module.md
├── context/             # Bilgi tabanı
│   ├── module-registry.md       # 29 modül listesi
│   ├── api-surface.md           # Tüm HTTP endpoint'ler
│   ├── architecture-summary.md  # Mimari özet
│   └── conventions.md           # Kod kuralları
└── templates/           # Modül iskelet şablonları
    └── module/ (8 dosya)
```

## AI Araç Yönlendirmeleri

Her AI aracı kendi keşif dosyasından `.sentrybot/`'a yönlendirilir:

| Araç | Keşif Dosyası | İçerik |
|------|--------------|--------|
| **OpenCode** | `.opencode/agents/` + `.opencode/skills/` | İnce yönlendirici → `.sentrybot/` |
| **Claude Code** | `CLAUDE.md` | İnce yönlendirici → `.sentrybot/` |
| **Copilot** | `.github/agents/` + `.github/copilot-instructions.md` | İnce yönlendirici → `.sentrybot/` |
| **Cursor** | `.cursor/rules/*.mdc` | Akıllı kurallar (globs) → `.sentrybot/` |
| **Windsurf** | `.windsurfrules` | İnce yönlendirici → `.sentrybot/` |
| **Antigravity** | `AGENTS.md` (bu dosya) | İnce yönlendirici → `.sentrybot/` |

### Global Kurulum

**OpenCode:**
```bash
cp -r .opencode/agents/* ~/.config/opencode/agents/
cp -r .opencode/skills/* ~/.config/opencode/skills/
```

**Claude Code:**
```bash
cp CLAUDE.md ~/.claude/CLAUDE.md
```

## Kritik Kurallar

1. **DryCode** — Tekrar yok, sade, net
2. **Arduino kontratı** — `contract.py` builder zorunlu
3. **Config** — Hardcode yasak, YAML'den oku
4. **Test** — Her modülde smoke test zorunlu
5. **Modül yapısı** — `x<Name>Service.py` + `config_loader.py` + `api/router.py`

## Hızlı Başlangıç

| Görev | Oku |
|-------|-----|
| Yeni modül oluştur | `.sentrybot/agents/module-creator.md` → `.sentrybot/skills/scaffold-module.md` |
| Modülü düzenle | `.sentrybot/agents/module-editor.md` → ilgili skill |
| PR/Issue oluştur | `.sentrybot/agents/github-ops.md` → `create-pr.md` / `create-issue.md` |
| Modüller arası bağlantı | `.sentrybot/agents/inter-module.md` → `module-dependency-map.md` |
| Kod incele | `.sentrybot/agents/code-reviewer.md` |
