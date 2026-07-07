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


from modules.autonomy.services.companion_lines import CompanionLineGenerator


def test_proactive_uses_social_hint_in_needs_line():
    gen = CompanionLineGenerator(None, {"use_llm": False})
    line = gen._needs_line(
        "proactive",
        {
            "speaker": "Emir",
            "social_hint": "likes satranc",
            "needs": {"social": 40},
            "owner_present": True,
            "dominant_emotion": "neutral",
        },
    )
    assert line and "satranc" in line.lower()


def test_proactive_skips_social_hint_when_trust_low():
    p = ProactivePlanner({"callback_min_trust": 0.3})
    line = p._generate_line(
        kind="proactive",
        mood="neutral",
        speaker="Emir",
        owner_present=True,
        needs={"social": 50},
        social_profile={"likes": ["satranc"], "trust_score": 0.1},
    )
    assert line
    assert "satranc" not in line.lower()
