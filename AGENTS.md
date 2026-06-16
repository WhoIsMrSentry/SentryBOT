# SentryBOT — AI Agent Entry Point

**Tek merkez:** `.sentrybot/AI_HUB.md`

Tüm agent, skill, context, sub-agent ve Obsidian notları `.sentrybot/` dizininde toplanmıştır.
Bir göreve başlamadan önce `.sentrybot/AI_HUB.md` dosyasını oku.

## Kritik Kurallar
1. DryCode — tekrar yok, tek sorumluluk
2. Modül yapısı — `x<Name>Service.py` + `config_loader.py` + `api/router.py`
3. Arduino kontratı — `contract.py` builder zorunlu, elle payload YASAK
4. Config — hardcode YASAK, YAML'den oku
5. Test — her modülde `tests/test_smoke.py` zorunlu
