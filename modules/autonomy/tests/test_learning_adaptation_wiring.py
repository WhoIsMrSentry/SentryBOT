"""Trust-aware enrichment and proactive callbacks after feedback learning."""

from __future__ import annotations

from pathlib import Path

from modules.autonomy.services.brain import AutonomyBrain
from modules.autonomy.services.proactive_planner import ProactivePlanner
from modules.social_db.db import SocialDB


def _minimal_brain(tmp_path):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    cfg = {
        "companion": {"enabled": True, "learning": {"enabled": True}},
        "endpoints": {},
        "defaults": {},
        "behaviors": {},
        "owner": {},
        "vision_hooks": {},
    }
    brain = AutonomyBrain.__new__(AutonomyBrain)
    brain.config = cfg
    brain.relationship_memory = type("RM", (), {})()
    brain.relationship_memory.social_profile = lambda name: {  # type: ignore
        "name": name,
        "likes": ["satranc"],
        "topics": [],
        "trust_score": 0.8,
        "top_memory": "",
    }
    brain.relationship_memory.recall_candidates = lambda name, limit=12: []  # type: ignore
    brain.client = type("C", (), {"push_interaction_event": lambda *a, **k: None})()
    return brain


def test_enrichment_injects_trust_hint(tmp_path):
    brain = _minimal_brain(tmp_path)
    out = brain._enrich_user_text_with_companion_context("bugun ne yapalim", speaker="Emir")
    assert "trust=high" in out
    assert "likes=satranc" in out


def test_proactive_callback_uses_high_trust_warm_line():
    p = ProactivePlanner({"enable_callback_lines": True, "callback_min_trust": 0.2})
    line = p._callback_line(
        {"name": "Emir", "likes": ["satranc"], "topics": [], "trust_score": 0.85, "last_user_utterance": ""},
        speaker="Emir",
        owner_present=True,
    )
    assert line and "satranc" in line.lower()


def test_proactive_skips_callback_when_trust_too_low():
    p = ProactivePlanner({"enable_callback_lines": True, "callback_min_trust": 0.3})
    line = p._callback_line(
        {"name": "Emir", "likes": ["satranc"], "topics": [], "trust_score": 0.1, "last_user_utterance": ""},
        speaker="Emir",
        owner_present=True,
    )
    assert line == ""
