# Skill: Arduino Contract — Arduino Kontrat Builder Ekleme

> Arduino komut builder ve validator fonksiyonu ekleme prosedürü.

## Tek Kaynak
Tüm Arduino komutlarının tek kaynağı: `modules/arduino_serial/contract.py`

## Mevcut Builder Örnekleri İncele
```bash
cat modules/arduino_serial/contract.py
```
Mevcut `build_*` ve `validate_*` fonksiyonlarının kalıbını incele.

## Yeni Komut Ekleme

### Adım 1: Builder Fonksiyonu
```python
# modules/arduino_serial/contract.py içine ekle:

def build_{{command_name}}({{parametreler}}) -> dict:
    """{{Komut açıklaması}}."""
    payload = {
        "cmd": "{{command_name}}",
        {{alanlar}}
    }
    validate_{{command_name}}(payload)
    return payload
```

### Adım 2: Validator Fonksiyonu
```python
def validate_{{command_name}}(payload: dict) -> None:
    """{{command_name}} payload doğrulama."""
    assert payload.get("cmd") == "{{command_name}}"
    # Alan doğrulamaları
    {{doğrulama_kuralları}}
```

### Adım 3: Test Yaz (Zorunlu)
```python
# modules/arduino_serial/tests/ içine:
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

### Adım 4: Gateway Davranış Testi
`/arduino/request` endpoint'inin yeni komutu doğru işlediğini test et.

## Zorunlu PR Kontrol Listesi
- [ ] `contract.py`'ye builder eklendi
- [ ] `contract.py`'ye validator eklendi
- [ ] Validator unit testi yazıldı
- [ ] Gateway davranış testi yazıldı
- [ ] Kritik komutsa `/arduino/request` kullanılıyor (fire-and-forget değil)
- [ ] Timeout 0.8-1.5s arasında
- [ ] PR açıklamasında kontrat uyumu belirtildi
