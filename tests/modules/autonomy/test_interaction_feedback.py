"""InteractionFeedbackLearner: praise/rude -> trust_score and moments."""

from __future__ import annotations

from pathlib import Path

from modules.autonomy.services.interaction_feedback import InteractionFeedbackLearner
from modules.social_db.db import SocialDB


def test_praise_raises_trust(tmp_path):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    db.persons.upsert(name="Emir", trust_score=0.4)
    fb = InteractionFeedbackLearner(social_db=db)
    new = fb.apply("user_praise", speaker="Emir", text="aferin cok iyisin")
    assert new is not None and new > 0.4
    assert db.persons.get_by_name("Emir")["trust_score"] == new


def test_rude_lowers_trust(tmp_path):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    db.persons.upsert(name="Emir", trust_score=0.6)
    fb = InteractionFeedbackLearner(social_db=db)
    new = fb.apply("user_rude", speaker="Emir", text="aptal robot")
    assert new is not None and new < 0.6


def test_unknown_event_is_noop(tmp_path):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    db.persons.upsert(name="Emir", trust_score=0.5)
    fb = InteractionFeedbackLearner(social_db=db)
    assert fb.apply("scene_change", speaker="Emir") is None


def test_disabled_never_changes_trust(tmp_path):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    db.persons.upsert(name="Emir", trust_score=0.5)
    fb = InteractionFeedbackLearner({"enabled": False}, social_db=db)
    assert fb.apply("user_praise", speaker="Emir") is None
