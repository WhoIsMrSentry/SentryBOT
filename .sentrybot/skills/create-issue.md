# Skill: Create Issue — Issue Oluşturma

> GitHub Issue standartlarına uygun bug report ve feature request oluşturma.

## Bug Report

`.github/ISSUE_TEMPLATE/bug_report.yml` formatına uygun:

```markdown
**Açıklama:** <Hatanın kısa açıklaması>

**Beklenen davranış:** <Ne olması gerekiyordu>

**Gerçekleşen davranış:** <Ne oldu>

**Tekrar adımları:**
1. <Adım 1>
2. <Adım 2>
3. <Adım 3>

**Ortam:**
- Platform: Raspberry Pi 5
- Python: 3.10
- OS: <Raspbian/Ubuntu>
- Etkilenen modül: <modül adı>

**Log çıktısı:**
\```
<ilgili log satırları>
\```

**Ekran görüntüsü:** (varsa)
```

## Feature Request

`.github/ISSUE_TEMPLATE/feature_request.yml` formatına uygun:

```markdown
**Motivasyon:** <Neden bu özellik gerekli>

**Kullanım senaryosu:** <Nasıl kullanılacak>

**Önerilen çözüm:** <Teknik yaklaşım>

**Alternatifler:** <Düşünülen diğer yollar>

**Etkilenecek modüller:** <modül listesi>

**Ek bilgi:** (varsa)
```

## Label Önerisi

| Durum | Label |
|-------|-------|
| Bug | `bug` |
| Feature | `enhancement` |
| Acil | `priority:high` |
| Dokümantasyon | `documentation` |
| Arduino ile ilgili | `hardware:arduino` |
