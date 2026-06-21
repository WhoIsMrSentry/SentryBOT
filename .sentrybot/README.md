# SentryBOT AI Agent & Skill Sistemi

Bu dizin, SentryBOT deposunda çalışan **tüm AI kodlama asistanları** için yapılandırılmış agent tanımları, skill dosyaları, context bilgileri ve şablonlar içerir.

## Desteklenen AI Araçları

| Araç | Keşif Dosyası | Durum |
|------|--------------|-------|
| **Claude Code** | `CLAUDE.md` (kök dizin) | ✅ |
| **GitHub Copilot** | `.github/copilot-instructions.md` + `.github/agents/` | ✅ |
| **Cursor** | `.cursorrules` (kök dizin) | ✅ |
| **Windsurf** | `.windsurfrules` (kök dizin) | ✅ |
| **OpenCode** | `AGENTS.md` (kök dizin) | ✅ |
| **Aider** | `AGENTS.md` (kök dizin) | ✅ |
| **Antigravity** | `AGENTS.md` (kök dizin) | ✅ |

## Dizin Yapısı

```
.sentrybot/
├── README.md                    ← Bu dosya
├── agents/                      # İş akışı yöneticileri
│   └── sub/                     # Modül bazlı sub-agent dosyaları
│   ├── module-creator.md        # 🏗️ Yeni modül oluşturma
│   ├── module-editor.md         # ✏️ Mevcut modül düzenleme
│   ├── github-ops.md            # 🐙 GitHub işlemleri (PR/Issue/CI)
│   ├── inter-module.md          # 🔗 Modüller arası etkileşim
│   └── code-reviewer.md         # 🔍 Kod inceleme
├── skills/                      # Adım adım prosedürler
│   └── modules/                 # Modül bazlı skill dosyaları
│   ├── scaffold-module.md       # Modül iskeleti oluşturma
│   ├── add-api-endpoint.md      # API endpoint ekleme
│   ├── add-service-class.md     # Service class ekleme
│   ├── update-config.md         # Config güncelleme
│   ├── write-tests.md           # Test yazma
│   ├── write-architecture-doc.md# Mimari dok yazma
│   ├── arduino-contract.md      # Arduino kontrat ekleme
│   ├── gateway-bootstrap.md     # Gateway modül kaydı
│   ├── create-pr.md             # PR oluşturma
│   ├── create-issue.md          # Issue oluşturma
│   ├── module-dependency-map.md # Bağımlılık haritası
│   └── debug-module.md          # Debugging
├── context/                     # Bilgi tabanı
│   ├── module-registry.md       # 29 modülün listesi
│   ├── api-surface.md           # Tüm HTTP endpoint'ler
│   ├── architecture-summary.md  # Mimari özet
│   └── conventions.md           # Kod kuralları
├── obsidian/                    # Obsidian bilgi kasası notları
│   └── modules/                 # Modül bazlı bilgi notları
├── tools/                       # AI varlık üretici scriptleri
└── templates/                   # İskelet şablonları
    └── module/                  # Modül dosya şablonları
        ├── __init__.py.tmpl
        ├── xService.py.tmpl
        ├── config_loader.py.tmpl
        ├── config.yml.tmpl
        ├── router.py.tmpl
        ├── test_smoke.py.tmpl
        ├── architecture.md.tmpl
        └── README.md.tmpl
```

## Kullanım

### AI Asistan ile Çalışırken

1. **İlk adım:** İlgili context dosyasını oku (modül listesi, API yüzeyi, kurallar)
2. **Görev seç:** Uygun agent dosyasını oku (module-creator, module-editor, vb.)
3. **Uygula:** Agent'ın referans verdiği skill dosyalarını adım adım takip et
4. **Doğrula:** Testleri çalıştır, dokümantasyonu güncelle

### Yeni Modül Oluşturma Örneği

```
AI Asistana: "Yeni bir ultrasonik sensör modülü oluştur"

AI Asistan:
1. .sentrybot/context/module-registry.md → mevcut modülleri öğrenir
2. .sentrybot/agents/module-creator.md → iş akışını takip eder
3. .sentrybot/skills/scaffold-module.md → iskelet oluşturur
4. .sentrybot/skills/gateway-bootstrap.md → Gateway'e kaydeder
5. .sentrybot/skills/write-tests.md → test yazar
```

## Güncelleme

Bu dosyalar depoyla birlikte güncel tutulmalıdır:
- Yeni modül eklendiğinde → `context/module-registry.md` güncellenir
- Yeni endpoint eklendiğinde → `context/api-surface.md` güncellenir
- Kural değiştiğinde → `context/conventions.md` güncellenir


## Modül Bazlı AI Varlıkları (Yeni)

Aşağıdaki içerikler otomatik üretilir:
- `.sentrybot/skills/modules/*.md`
- `.sentrybot/agents/sub/*.md`
- `.sentrybot/obsidian/modules/*.md`

Üretmek/güncellemek için:

```bash
python3 .sentrybot/tools/generate_module_ai_assets.py
```
