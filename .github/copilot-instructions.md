# Copilot Instructions - SentryBOT Single Source of Truth

Bu depoda agent, skill, context ve template icin tek kaynak `.sentrybot/` dizinidir.

## Canonical Kaynaklar
- Agent tanimlari: `.sentrybot/agents/`
- Skill prosedurleri: `.sentrybot/skills/`
- Context bilgisi: `.sentrybot/context/`
- Sablonlar: `.sentrybot/templates/`

## Copilot Calisma Kurallari (Ozet)
1. DryCode: tekrar yok, tek sorumluluk, kisa fonksiyonlar.
2. Arduino payloadlari yalnizca `modules/arduino_serial/contract.py` builder fonksiyonlari ile uretilir.
3. Hardcode config kullanma; `config.yml` + `config_loader.py` kalibini uygula.
4. Her modulde en az smoke test bulundur.
5. Moduller arasi HTTP etkilesimlerinde timeout ve hata toleransi zorunludur.

## Calisma Sirasi
1. Ilgili context dosyalarini oku (`.sentrybot/context/*`).
2. Uygun agent dosyasini oku (`.sentrybot/agents/*`).
3. Agentin referans verdigi skill dosyalarini uygula (`.sentrybot/skills/*`).

## Adapter Kurali
`.github/agents/`, `.opencode/`, `.cursor/skills/` altindaki dosyalar ince yonlendiricidir.
Asil is kurallari her zaman `.sentrybot/` altindadir.
