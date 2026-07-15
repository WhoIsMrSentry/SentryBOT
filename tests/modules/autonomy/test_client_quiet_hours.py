from __future__ import annotations

from modules.autonomy.services.client import ServiceClient


class _CaptureClient(ServiceClient):
    def __init__(self, cfg=None):
        super().__init__({}, config=cfg or {})
        self.last_payload = None

    def _post(self, service, endpoint, json=None, params=None):
        self.last_payload = {
            "service": service,
            "endpoint": endpoint,
            "json": json,
            "params": params,
        }
        return {"ok": True}


def test_speak_quiet_hours_applies_tone_and_trim():
    c = _CaptureClient(
        {
            "speech_quiet_hours": {
                "enabled": True,
                "start": "23:00",
                "end": "07:00",
                "tone": "calm",
                "max_chars": 10,
            }
        }
    )
    c._quiet_hours_active = lambda: True  # type: ignore[assignment]

    c.speak("123456789012345")

    assert c.last_payload is not None
    payload = c.last_payload["json"]
    assert payload["tone"] == "calm"
    assert payload["text"].endswith("...")
    assert len(payload["text"]) <= 10


def test_speak_keeps_explicit_tone_in_quiet_hours():
    c = _CaptureClient(
        {
            "speech_quiet_hours": {
                "enabled": True,
                "start": "23:00",
                "end": "07:00",
                "tone": "calm",
                "max_chars": 50,
            }
        }
    )
    c._quiet_hours_active = lambda: True  # type: ignore[assignment]

    c.speak("Merhaba", tone="excited")

    assert c.last_payload is not None
    payload = c.last_payload["json"]
    assert payload["tone"] == "excited"
