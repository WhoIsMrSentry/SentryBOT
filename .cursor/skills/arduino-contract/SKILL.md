---
name: arduino-contract
description: SentryBOT: Arduino Contract â€” Arduino Kontrat Builder Ekleme. Source: .sentrybot/skills/arduino-contract.md
---
# Skill: Arduino Contract â€” Arduino Kontrat Builder Ekleme

> Arduino komut builder ve validator fonksiyonu ekleme prosedÃ¼rÃ¼.

## Tek Kaynak
TÃ¼m Arduino komutlarÄ±nÄ±n tek kaynaÄŸÄ±: `modules/arduino_serial/contract.py`

## Mevcut Builder Ã–rnekleri Ä°ncele
```bash
cat modules/arduino_serial/contract.py
```
Mevcut `build_*` ve `validate_*` fonksiyonlarÄ±nÄ±n kalÄ±bÄ±nÄ± incele.

## Yeni Komut Ekleme

### AdÄ±m 1: Builder Fonksiyonu
```python
# modules/arduino_serial/contract.py iÃ§ine ekle:

def build_{{command_name}}({{parametreler}}) -> dict:
    """{{Komut aÃ§Ä±klamasÄ±}}."""
    payload = {
        "cmd": "{{command_name}}",
        {{alanlar}}
    }
    validate_{{command_name}}(payload)
    return payload
```

### AdÄ±m 2: Validator Fonksiyonu
```python
def validate_{{command_name}}(payload: dict) -> None:
    """{{command_name}} payload doÄŸrulama."""
    assert payload.get("cmd") == "{{command_name}}"
    # Alan doÄŸrulamalarÄ±
    {{doÄŸrulama_kurallarÄ±}}
```

### AdÄ±m 3: Test Yaz (Zorunlu)
```python
# modules/arduino_serial/tests/ iÃ§ine:
def test_build_{{command_name}}():
    from modules.arduino_serial.contract import build_{{command_name}}
    payload = build_{{command_name}}({{test_parametreleri}})
    assert payload["cmd"] == "{{command_name}}"

def test_validate_{{command_name}}_invalid():
    from modules.arduino_serial.contract import validate_{{command_name}}
    import pytest
    with pytest.raises(AssertionError):
        validate_{{command_name}}({"cmd": "wrong"})
```

### AdÄ±m 4: Gateway DavranÄ±ÅŸ Testi
`/arduino/request` endpoint'inin yeni komutu doÄŸru iÅŸlediÄŸini test et.

## Zorunlu PR Kontrol Listesi
- [ ] `contract.py`'ye builder eklendi
- [ ] `contract.py`'ye validator eklendi
- [ ] Validator unit testi yazÄ±ldÄ±
- [ ] Gateway davranÄ±ÅŸ testi yazÄ±ldÄ±
- [ ] Kritik komutsa `/arduino/request` kullanÄ±lÄ±yor (fire-and-forget deÄŸil)
- [ ] Timeout 0.8-1.5s arasÄ±nda
- [ ] PR aÃ§Ä±klamasÄ±nda kontrat uyumu belirtildi

