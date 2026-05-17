---
name: create-pr
description: SentryBOT: Create PR â€” Pull Request OluÅŸturma. Source: .sentrybot/skills/create-pr.md
---
# Skill: Create PR â€” Pull Request OluÅŸturma

> SentryBOT PR standartlarÄ±na uygun Pull Request hazÄ±rlama prosedÃ¼rÃ¼.

## Branch AdlandÄ±rma

| TÃ¼r | Format | Ã–rnek |
|-----|--------|-------|
| Yeni Ã¶zellik | `feat/<modÃ¼l>-<aÃ§Ä±klama>` | `feat/speech-multi-language` |
| Hata dÃ¼zeltme | `fix/<modÃ¼l>-<aÃ§Ä±klama>` | `fix/vlm-tracker-crash` |
| Refactor | `refactor/<modÃ¼l>-<aÃ§Ä±klama>` | `refactor/autonomy-mood-engine` |
| DokÃ¼mantasyon | `docs/<aÃ§Ä±klama>` | `docs/update-architecture` |

## PR Åablonu

`.github/pull_request_template.md` doldurulur:

```markdown
## Ã–zet
Ne deÄŸiÅŸti ve neden deÄŸiÅŸti?
<KÄ±sa aÃ§Ä±klama>

## DeÄŸiÅŸiklik tipi
- [ ] Hata dÃ¼zeltmesi
- [ ] Yeni Ã¶zellik
- [ ] Refactor
- [ ] DokÃ¼mantasyon gÃ¼ncellemesi
- [ ] Test gÃ¼ncellemesi

## Etkilenen modÃ¼ller
<modules/x, modules/y>

## DoÄŸrulama
- [ ] Lokal Ã§alÄ±ÅŸtÄ±rma tamamlandÄ±
- [ ] Ä°lgili testler geÃ§iyor
- [ ] Gerekli dokÃ¼man/konfig gÃ¼ncellemeleri yapÄ±ldÄ±

## Arduino Kontrat KontrolÃ¼ (uygunsa)
- [ ] `contract.py` dÄ±ÅŸÄ±nda elle Arduino payload yazÄ±lmadÄ±
- [ ] Kritik komutlar `/arduino/request` kullanÄ±yor
- [ ] Yeni komut ailesi builder + validator + test iÃ§eriyor

## Risk ve geri alma
<AÃ§Ä±klama>

## Ä°lgili issue
Closes #<issue-number>
```

## Label Atama

DeÄŸiÅŸtirilen dosya yollarÄ±na gÃ¶re otomatik label ata (`.github/labeler.yml` kurallarÄ±).

## Git KomutlarÄ±

```bash
# Branch oluÅŸtur
git checkout -b feat/{{module}}-{{description}}

# DeÄŸiÅŸiklikleri ekle
git add modules/{{module}}/ .sentrybot/ docs/

# Commit (aÃ§Ä±klayÄ±cÄ± mesaj)
git commit -m "feat({{module}}): {{kÄ±sa aÃ§Ä±klama}}"

# Push
git push origin feat/{{module}}-{{description}}
```

## Commit MesajÄ± FormatÄ±

```
<tÃ¼r>(<kapsam>): <aÃ§Ä±klama>

Ã–rnekler:
feat(speech): add multi-language ASR support
fix(vlm): fix CSRT tracker crash on lost face
refactor(autonomy): extract mood engine to separate class
docs(architecture): update inter-module diagram
test(neopixel): add emotion palette unit tests
```

