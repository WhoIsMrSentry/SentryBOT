from __future__ import annotations

LANGUAGE_NAMES = {
    "tr": "Turkish",
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
}


def get_language_name(lang: str | None) -> str:
    code = str(lang or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return LANGUAGE_NAMES.get(code, code.upper() if code else "")


__all__ = ["LANGUAGE_NAMES", "get_language_name"]
