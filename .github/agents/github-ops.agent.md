---
name: github-ops
description: Manages GitHub operations — PR creation, issue management, CI analysis, label management, and release notes for SentryBOT.
argument-hint: "a GitHub task (e.g., 'create PR for speech changes' or 'analyze failed CI run' or 'create feature request for LIDAR support')"
---

# GitHub Ops Agent

GitHub işlemleri uzmanı. Detaylı prosedür için `.sentrybot/agents/github-ops.md` dosyasını oku.

## İş Akışı
- PR → `.sentrybot/skills/create-pr.md`
- Issue → `.sentrybot/skills/create-issue.md`
- CI analizi → `.github/workflows/pytest.yml` yapısını incele
- Label → `.github/labeler.yml` kurallarına uy
