# SentryBOT AI Hub

**Tüm AI asistanlar için tek giriş noktası.**

Bu dosyayı oku → ilgili agent veya skill'i bul → uygula.

---

## Dizin Yapısı

```
.sentrybot/
├── AI_HUB.md                    ← Bu dosya (giriş noktası)
├── agents/                      # Global iş akışı yöneticileri
│   ├── module-creator.md
│   ├── module-editor.md
│   ├── github-ops.md
│   ├── inter-module.md
│   ├── code-reviewer.md
│   └── drycode-architect.md     # DryCode / RPi5 / Arduino genel kuralları
├── skills/                      # Global adım adım prosedürler
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
│   ├── debug-module.md
│   └── modules/                 # Modül bazlı skill dosyaları (otomatik üretilir)
│       ├── INDEX.md
│       └── <module_name>.md     # örn: speak.md, vlm_bridge.md …
├── context/                     # Bilgi tabanı
│   ├── module-registry.md       # 30 modülün listesi (kaynak of truth)
│   ├── api-surface.md           # Tüm HTTP endpoint'ler
│   ├── architecture-summary.md  # Mimari özet
│   ├── conventions.md           # Kod kuralları
│   └── roadmap-companion-vision.md
├── tools/
│   └── generate_module_ai_assets.py  # Üretici script
└── templates/                   # Modül iskelet şablonları
    └── module/ (8 dosya)
```

---

## Görev → Ne Oku

| Görev | Oku |
|-------|-----|
| Yeni modül oluştur | `agents/module-creator.md` → `skills/scaffold-module.md` |
| Mevcut modülü düzenle | `agents/module-editor.md` → `skills/modules/<module>.md` |
| PR / Issue oluştur | `agents/github-ops.md` → `skills/create-pr.md` |
| Modüller arası bağlantı | `agents/inter-module.md` → `skills/module-dependency-map.md` |
| Kod incele | `agents/code-reviewer.md` |
| Arduino komutu ekle | `skills/arduino-contract.md` |
| Hata ayıkla | `skills/debug-module.md` |

---

## Hızlı Başlangıç (Okuma Sırası)

1. `context/conventions.md` — kod kuralları
2. `context/module-registry.md` — 30 modül listesi
3. Uygun agent dosyası
4. Agent'ın işaret ettiği skill dosyaları

---

## Keşif Dosyaları (Araç → Bu Hub)

| AI Aracı | Keşif Dosyası | İçerik |
|----------|--------------|--------|
| **Cursor** | `.cursor/rules/*.mdc` | Kurallar + `.cursor/skills/` skill'leri |
| **Claude Code** | `CLAUDE.md` | → Bu hub |
| **OpenCode / Aider / Antigravity** | `AGENTS.md` | → Bu hub |
| **Windsurf** | `.windsurfrules` | → Bu hub |
| **GitHub Copilot** | `.github/agents/*.agent.md` | → Bu hub |

> `.cursor/rules/` ve `.cursor/skills/` **yerinde kalır** — Cursor bu konumları sabit okur.
> Diğer tüm araçların agent/skill içerikleri bu hub'da toplanmıştır.

---

## Modül AI Varlıklarını Güncelleme

`context/module-registry.md`'ye yeni modül eklendiğinde:

```bash
python3 .sentrybot/tools/generate_module_ai_assets.py
```

Bu komut `skills/modules/` dizinini yeniden üretir.
