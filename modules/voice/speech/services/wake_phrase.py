from __future__ import annotations

WAKE_PHRASES = ("hey mycroft", "mycroft", "hey sentrybot", "hey sentry", "sentrybot", "sentry")


def contains_wakeword(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(phrase in lowered for phrase in WAKE_PHRASES)


def strip_wakewords(text: str) -> str:
    lowered = str(text or "").strip().lower()
    for phrase in WAKE_PHRASES:
        lowered = lowered.replace(phrase, " ")
    return " ".join(lowered.split())
