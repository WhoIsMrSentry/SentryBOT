---
name: write-tests
description: "SentryBOT modülleri için smoke, unit, API ve mock testleri yazar. CI uyumlu test kalıpları."
---

# Write Tests

## Test Türleri
1. **Smoke Test** (zorunlu) — import, config, service init, router
2. **Unit Test** — tek fonksiyon/class izole test
3. **API Test** — FastAPI TestClient ile endpoint testi
4. **Mock** — donanım/HTTP/Arduino bağımlılıkları mock

## CI Kuralları
- Python 3.10 hedef
- `--maxfail=1`
- Donanım testleri `@pytest.mark.skipif` ile korunur

## Tam Kalıplar
`.sentrybot/skills/write-tests.md` dosyasını oku.
