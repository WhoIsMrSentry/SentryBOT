"""Map speech, vision, and lifecycle signals to affective appraisal events."""

from __future__ import annotations

from typing import Optional

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")


def turkish_characters_present(text: str) -> bool:
    return any(ch in _TR_CHARS for ch in str(text or ""))


def speech_appraisal_event(text: str) -> Optional[str]:
    """Return an appraisal event name for spoken text, or ``None``."""
    low = str(text or "").lower().strip()
    if not low:
        return None

    insult = (
        "gerizekalı", "gerizekali", "orospu", "piç", "pic ", "siktir", "amk", "aq ",
        "fuck you", "go to hell",
    )
    rude = (
        "aptal", "salak", "gerizekal", "kapa cen", "sus ", "stupid", "shut up", "idiot",
    )
    thanks = (
        "teşekkür", "tesekkur", "sağ ol", "sag ol", "thanks", "thank you", "thank u",
        "merci", "gracias", "danke",
    )
    praise = (
        "aferin", "harikasın", "harikasin", "cok iyi", "çok iyi", "sevimlisin",
        "seviyorum", "good job", "well done", "i love you", "bravo",
    )
    petted = (
        "okşa", "oksa", "okşadım", "cok tatlisin", "çok tatlısın", "good boy",
        "good robot", "aferin sana", "seviyorum seni",
    )
    played = (
        "oyna", "oyunalim", "oyun oyna", "play with me", "let's play", "lets play",
        "benimle oyna",
    )

    if any(tok in low for tok in insult):
        return "user_insult"
    if any(tok in low for tok in rude):
        return "user_rude"
    if any(tok in low for tok in thanks):
        return "user_thanks"
    if any(tok in low for tok in petted):
        return "petted"
    if any(tok in low for tok in played):
        return "played_with"
    if any(tok in low for tok in praise):
        return "user_praise"
    return None


__all__ = ["speech_appraisal_event", "turkish_characters_present"]
