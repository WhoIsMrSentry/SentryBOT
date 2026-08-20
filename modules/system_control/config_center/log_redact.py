from __future__ import annotations

import re

_KEY_IN_URL = re.compile(r"(key=)([^&\s\"']+)", re.IGNORECASE)
_BEARER = re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]+)", re.IGNORECASE)


def redact_secrets(text: object) -> str:
    """Remove API keys and tokens from log-safe strings."""
    msg = str(text or "")
    msg = _KEY_IN_URL.sub(r"\1***", msg)
    msg = _BEARER.sub(r"\1***", msg)
    return msg
