from __future__ import annotations

import re
from typing import List

_TOKEN_RE = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+", re.UNICODE)
_TR_DEVOICE = str.maketrans({"ğ": "k", "d": "t", "b": "p", "c": "ç"})


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(str(text or "")) if len(t) > 1]


def _stem_tokens(text: str) -> set[str]:
    words = _tokens(text)
    out = set(words)
    for w in words:
        if len(w) >= 4:
            out.add(f"#{w[:4]}")
        if len(w) >= 5:
            p5 = w[:5]
            out.add(f"#{p5[:-1] + p5[-1].translate(_TR_DEVOICE)}")
    return out


__all__ = ["_TOKEN_RE", "_TR_DEVOICE", "_tokens", "_stem_tokens"]
