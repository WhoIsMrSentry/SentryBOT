# SentryBOT — AI Agent Entry Point

**Tek merkez:** `.sentrybot/AI_HUB.md`

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
│   ├── arduino-contract.md
│   ├── gateway-bootstrap.md
│   ├── create-pr.md
│   ├── create-issue.md
│   ├── module-dependency-map.md
│   └── debug-module.md
├── context/             # Bilgi tabanı
│   ├── (MCP ile değiştirildi)    # search_graph ile modül/route sorgulama
│   ├── architecture-summary.md  # Mimari özet
│   ├── conventions.md           # Kod kuralları
│   └── roadmap-companion-vision.md  # Proje yol haritası
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
1. DryCode — tekrar yok, tek sorumluluk
2. Modül yapısı — `x<Name>Service.py` + `config_loader.py` + `api/router.py`
3. Arduino kontratı — `contract.py` builder zorunlu, elle payload YASAK
4. Config — hardcode YASAK, YAML'den oku
5. Test — her modülde `tests/test_smoke.py` zorunlu
