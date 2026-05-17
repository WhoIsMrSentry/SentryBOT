from __future__ import annotations

from modules.speech.services.wake_phrase import contains_wakeword, strip_wakewords


def test_contains_wakeword() -> None:
    assert contains_wakeword("hey sentrybot")
    assert contains_wakeword("Hey Sentry, what is up")
    assert not contains_wakeword("merhaba nasılsın")


def test_strip_wakewords() -> None:
    assert strip_wakewords("hey sentrybot please help") == "please help"
    assert strip_wakewords("hey sentrybot") == ""
