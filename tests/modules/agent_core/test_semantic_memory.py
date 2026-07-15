"""Tests for the TF-IDF semantic index and episodic memory recall."""

from __future__ import annotations

from modules.agent_core.services.semantic_index import rank, tokenize, SemanticIndex
from modules.agent_core.services.memory import EpisodicMemory


def test_tokenize_keeps_unicode_turkish():
    toks = tokenize("Müziği çok seviyorum")
    assert "müziği" in toks
    assert "seviyorum" in toks


def test_rank_orders_by_relevance():
    docs = [
        "the cat sat on the mat",
        "robot arm calibration failed twice",
        "I love playing chess with you",
    ]
    ranked = rank("chess match", docs, top_k=3)
    assert ranked, "expected at least one relevant doc"
    assert ranked[0][0] == 2  # chess doc ranks first


def test_rank_ignores_common_words_via_idf():
    docs = [
        "the the the the the dog",
        "the the the the the cat",
    ]
    # 'the' is common (low idf); the distinguishing term must drive the result
    ranked = rank("dog", docs, top_k=2)
    assert ranked[0][0] == 0


def test_semantic_index_search():
    idx = SemanticIndex()
    idx.add("e1", "kitchen lights turned off")
    idx.add("e2", "owner left the house")
    hits = idx.search("lights", top_k=2)
    assert hits and hits[0][0] == "e1"


def test_memory_recall_without_literal_substring():
    mem = EpisodicMemory(":memory:")
    mem.remember("dialogue", "User: I love chess | Bot: great")
    mem.remember("dialogue", "User: calibrate the arm | Bot: done")
    mem.remember("observation", "saw a dog in the room")

    # query has no exact substring match, but shares the token 'chess'
    results = mem.search_memory("chess tonight", limit=2)
    assert results
    assert any("chess" in r["content"] for r in results)


def test_memory_recall_prefers_relevant_episode():
    mem = EpisodicMemory(":memory:")
    mem.remember("observation", "the weather is cold")
    mem.remember("observation", "the robot calibration routine completed")
    results = mem.search_memory("calibration status", limit=1)
    assert results
    assert "calibration" in results[0]["content"]
