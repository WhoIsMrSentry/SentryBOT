---
name: create-issue
description: SentryBOT: Create Issue â€” Issue OluÅŸturma. Source: .sentrybot/skills/create-issue.md
---
# Skill: Create Issue â€” Issue OluÅŸturma

> GitHub Issue standartlarÄ±na uygun bug report ve feature request oluÅŸturma.

## Bug Report

`.github/ISSUE_TEMPLATE/bug_report.yml` formatÄ±na uygun:

```markdown
**AÃ§Ä±klama:** <HatanÄ±n kÄ±sa aÃ§Ä±klamasÄ±>

**Beklenen davranÄ±ÅŸ:** <Ne olmasÄ± gerekiyordu>

**GerÃ§ekleÅŸen davranÄ±ÅŸ:** <Ne oldu>

**Tekrar adÄ±mlarÄ±:**
1. <AdÄ±m 1>
2. <AdÄ±m 2>
3. <AdÄ±m 3>

**Ortam:**
- Platform: Raspberry Pi 5
- Python: 3.10
- OS: <Raspbian/Ubuntu>
- Etkilenen modÃ¼l: <modÃ¼l adÄ±>

**Log Ã§Ä±ktÄ±sÄ±:**
\```
<ilgili log satÄ±rlarÄ±>
\```

**Ekran gÃ¶rÃ¼ntÃ¼sÃ¼:** (varsa)
```

## Feature Request

`.github/ISSUE_TEMPLATE/feature_request.yml` formatÄ±na uygun:

```markdown
**Motivasyon:** <Neden bu Ã¶zellik gerekli>

**KullanÄ±m senaryosu:** <NasÄ±l kullanÄ±lacak>

**Ã–nerilen Ã§Ã¶zÃ¼m:** <Teknik yaklaÅŸÄ±m>

**Alternatifler:** <DÃ¼ÅŸÃ¼nÃ¼len diÄŸer yollar>

**Etkilenecek modÃ¼ller:** <modÃ¼l listesi>

**Ek bilgi:** (varsa)
```

## Label Ã–nerisi

| Durum | Label |
|-------|-------|
| Bug | `bug` |
| Feature | `enhancement` |
| Acil | `priority:high` |
| DokÃ¼mantasyon | `documentation` |
| Arduino ile ilgili | `hardware:arduino` |

