from modules.autonomy.services.companion_lines import CompanionLineGenerator


class UnavailableClient:
    def __init__(self):
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        return {"ok": False, "error": "llm_model_unavailable"}


def test_companion_line_uses_template_when_llm_unavailable_and_cools_down():
    client = UnavailableClient()
    gen = CompanionLineGenerator(client, {"use_llm": True, "llm_cooldown_s": 100, "default_language": "tr"})

    first = gen.generate("proactive", dominant_emotion="neutral", needs={"stimulation": 80})
    second = gen.generate("proactive", dominant_emotion="neutral", needs={"stimulation": 80})

    assert first
    assert second
    assert client.calls == 1
