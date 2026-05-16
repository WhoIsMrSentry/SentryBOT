# Skill: Create PR — Pull Request Oluşturma

> SentryBOT PR standartlarına uygun Pull Request hazırlama prosedürü.

## Branch Adlandırma

| Tür | Format | Örnek |
|-----|--------|-------|
| Yeni özellik | `feat/<modül>-<açıklama>` | `feat/speech-multi-language` |
| Hata düzeltme | `fix/<modül>-<açıklama>` | `fix/vlm-tracker-crash` |
| Refactor | `refactor/<modül>-<açıklama>` | `refactor/autonomy-mood-engine` |
| Dokümantasyon | `docs/<açıklama>` | `docs/update-architecture` |

## PR Şablonu

`.github/pull_request_template.md` doldurulur:

```markdown
## Özet
Ne değişti ve neden değişti?
<Kısa açıklama>

## Değişiklik tipi
- [ ] Hata düzeltmesi
- [ ] Yeni özellik
- [ ] Refactor
- [ ] Dokümantasyon güncellemesi
- [ ] Test güncellemesi

## Etkilenen modüller
<modules/x, modules/y>

## Doğrulama
- [ ] Lokal çalıştırma tamamlandı
- [ ] İlgili testler geçiyor
- [ ] Gerekli doküman/konfig güncellemeleri yapıldı

## Arduino Kontrat Kontrolü (uygunsa)
- [ ] `contract.py` dışında elle Arduino payload yazılmadı
- [ ] Kritik komutlar `/arduino/request` kullanıyor
- [ ] Yeni komut ailesi builder + validator + test içeriyor

## Risk ve geri alma
<Açıklama>

## İlgili issue
Closes #<issue-number>
```

## Label Atama

Değiştirilen dosya yollarına göre otomatik label ata (`.github/labeler.yml` kuralları).

## Git Komutları

```bash
# Branch oluştur
git checkout -b feat/{{module}}-{{description}}

# Değişiklikleri ekle
git add modules/{{module}}/ .sentrybot/ docs/

# Commit (açıklayıcı mesaj)
git commit -m "feat({{module}}): {{kısa açıklama}}"

# Push
git push origin feat/{{module}}-{{description}}
```

## Commit Mesajı Formatı

```
<tür>(<kapsam>): <açıklama>

Örnekler:
feat(speech): add multi-language ASR support
fix(vlm): fix CSRT tracker crash on lost face
refactor(autonomy): extract mood engine to separate class
docs(architecture): update inter-module diagram
test(neopixel): add emotion palette unit tests
```
