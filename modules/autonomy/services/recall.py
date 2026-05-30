"""Context-aware proactive recall.

Given the user's *current* utterance and a pool of past snippets (moments,
preferences, prior lines), pick the snippet most relevant to what is being said
right now — so the robot can say "last time you mentioned X" naturally inside a
conversation instead of only on idle timers.

Prefers the agent_core TF-IDF semantic ranker when available, falling back to a
self-contained token-overlap score so autonomy never hard-depends on it.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set:
    return {t for t in _TOKEN_RE.findall(str(text).lower()) if len(t) > 2}


def _fallback_best(text: str, snippets: Sequence[str]) -> Optional[int]:
    q = _tokens(text)
    if not q:
        return None
    best_idx, best_score = None, 0.0
    for idx, snip in enumerate(snippets):
        s = _tokens(snip)
        if not s:
            continue
        overlap = len(q & s)
        if overlap == 0:
            continue
        score = overlap / len(q | s)
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx


def most_relevant(text: str, snippets: Sequence[str], min_score: float = 0.04) -> Optional[str]:
    """Return the snippet most relevant to ``text`` (or ``None``)."""
    cleaned: List[str] = [str(s).strip() for s in snippets if str(s).strip()]
    if not cleaned or not str(text).strip():
        return None

    try:
        from modules.agent_core.services.semantic_index import rank

        ranked = rank(text, cleaned, top_k=1)
        if ranked and ranked[0][1] >= min_score:
            return cleaned[ranked[0][0]]
        if ranked:
            return None
    except Exception:
        pass

    idx = _fallback_best(text, cleaned)
    return cleaned[idx] if idx is not None else None


__all__ = ["most_relevant"]
