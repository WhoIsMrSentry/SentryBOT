"""Dependency-light semantic retrieval (TF-IDF + cosine).

A pragmatic stand-in for a full embedding store (FAISS/Chroma) that needs **no**
extra dependencies, so it runs anywhere SentryBOT does — including a bare PC dev
checkout. It ranks documents against a query by TF-IDF cosine similarity, which
handles common-word noise (via IDF) and document length (via cosine) far better
than substring/Jaccard matching.

Unicode-aware tokenisation keeps Turkish text (ç, ğ, ı, ö, ş, ü) intact.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence, Tuple

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(str(text).lower()) if len(t) > 1]


def _tf(tokens: Sequence[str]) -> Dict[str, float]:
    counts = Counter(tokens)
    total = float(sum(counts.values())) or 1.0
    return {term: count / total for term, count in counts.items()}


def _idf(corpus_tokens: Sequence[Sequence[str]]) -> Dict[str, float]:
    n_docs = len(corpus_tokens)
    df: Counter = Counter()
    for tokens in corpus_tokens:
        for term in set(tokens):
            df[term] += 1
    # smoothed idf so a term in every doc still has a small positive weight
    return {term: math.log((1 + n_docs) / (1 + count)) + 1.0 for term, count in df.items()}


def _tfidf_vec(tokens: Sequence[str], idf: Dict[str, float]) -> Dict[str, float]:
    tf = _tf(tokens)
    return {term: freq * idf.get(term, 0.0) for term, freq in tf.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    # iterate over the smaller vector for the dot product
    if len(a) > len(b):
        a, b = b, a
    dot = sum(weight * b.get(term, 0.0) for term, weight in a.items())
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def rank(query: str, documents: Sequence[str], top_k: int = 5) -> List[Tuple[int, float]]:
    """Return ``[(doc_index, cosine_score), ...]`` sorted by descending relevance.

    Only documents with a positive similarity are returned. IDF is computed over
    the supplied document set plus the query.
    """
    q_tokens = tokenize(query)
    if not q_tokens or not documents:
        return []

    doc_tokens = [tokenize(d) for d in documents]
    idf = _idf(doc_tokens + [q_tokens])
    q_vec = _tfidf_vec(q_tokens, idf)

    scored: List[Tuple[int, float]] = []
    for idx, tokens in enumerate(doc_tokens):
        if not tokens:
            continue
        score = _cosine(q_vec, _tfidf_vec(tokens, idf))
        if score > 0.0:
            scored.append((idx, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[: max(0, int(top_k))]


class SemanticIndex:
    """Reusable in-memory index over ``(id, text)`` documents."""

    def __init__(self) -> None:
        self._ids: List[str] = []
        self._texts: List[str] = []

    def add(self, doc_id: str, text: str) -> None:
        self._ids.append(str(doc_id))
        self._texts.append(str(text))

    def __len__(self) -> int:
        return len(self._ids)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        return [(self._ids[i], score) for i, score in rank(query, self._texts, top_k)]


__all__ = ["tokenize", "rank", "SemanticIndex"]
