"""Tests for context-aware proactive recall."""

from __future__ import annotations

from modules.autonomy.services.recall import most_relevant


def test_picks_snippet_relevant_to_current_text():
    snippets = [
        "kullanici satranc kulubune gidiyor",
        "kullanici kahveyi sever",
        "kullanici izmirde yasiyor",
    ]
    hit = most_relevant("bugun satranc oynayalim mi", snippets)
    assert hit == "kullanici satranc kulubune gidiyor"


def test_returns_none_when_nothing_relevant():
    snippets = ["kullanici kahveyi sever", "kullanici izmirde yasiyor"]
    assert most_relevant("robotik kodlama dersi", snippets) is None


def test_empty_inputs_are_safe():
    assert most_relevant("", ["a b c"]) is None
    assert most_relevant("hello", []) is None
