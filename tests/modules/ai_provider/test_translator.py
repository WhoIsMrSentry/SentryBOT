from __future__ import annotations

from modules.ai_provider.services.translator import OllamaTranslator


class _FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, format=None, *, options=None, model=None):
        self.calls += 1
        content = messages[-1]["content"]
        if "to en" in content:
            return {"message": {"content": "hello"}}
        return {"message": {"content": "merhaba"}}


def test_translate_passthrough_same_language():
    tr = OllamaTranslator(_FakeClient(), {"enabled": True, "default_source_lang": "tr", "bridge_lang": "en"})
    text = tr.translate("merhaba", "tr", "tr")
    assert text == "merhaba"


def test_translate_bridge_and_back_with_cache():
    fake = _FakeClient()
    tr = OllamaTranslator(fake, {"enabled": True, "default_source_lang": "tr", "bridge_lang": "en", "cache_size": 4})

    en_text = tr.to_bridge("merhaba", "tr")
    assert en_text == "hello"

    en_text_cached = tr.to_bridge("merhaba", "tr")
    assert en_text_cached == "hello"

    tr_text = tr.from_bridge("hello", "tr")
    assert tr_text == "merhaba"
    assert fake.calls == 2


def test_detect_language_heuristic_turkish_chars():
    tr = OllamaTranslator(_FakeClient(), {"enabled": True, "default_source_lang": "en", "bridge_lang": "en"})
    detected = tr.detect_language("nasılsın bugün")
    assert detected == "tr"


def test_to_bridge_auto_uses_detected_language():
    fake = _FakeClient()
    tr = OllamaTranslator(fake, {"enabled": True, "default_source_lang": "en", "bridge_lang": "en"})
    out = tr.to_bridge("merhaba", "auto")
    assert out == "hello"
