from unittest.mock import MagicMock

from modules.autonomy.services.brain_parts.decision import DecisionMixin


class DummyBrain(DecisionMixin):
    def __init__(self):
        self.state = {
            "last_interaction": 0,
            "is_bored": False,
            "is_sleeping": True,
        }
        self.config = {"behaviors": {"sleep": {"enabled": True}}}
        self.memory = MagicMock()
        self.memory.get_recent_events.return_value = [
            "User said hello to SentryBOT",
            "SentryBOT detected face of Emir",
            "User asked about the weather",
        ]
        self.mood = MagicMock()
        self.mood.state = {"happiness": 70, "energy": 40, "curiosity": 65}
        self.world_memory = MagicMock()
        self.social_db = MagicMock()
        self.agent = MagicMock()


def test_dream_reflection_heuristic_fallback():
    brain = DummyBrain()
    brain.agent = None  # No LLM available
    res = brain._run_dream_reflection()
    assert res is not None
    assert res["kind"] == "episode"
    assert res["events_reviewed"] == 3
    assert res["llm_synthesized"] is False
    assert "Dream cycle reflection" in res["summary"]
    brain.world_memory.observe.assert_called_once()


def test_dream_reflection_with_llm():
    brain = DummyBrain()
    brain.agent.generate_reflection.return_value = "Kullanıcı Emir hava durumunu sordu ve robotu dostça selamladı."
    res = brain._run_dream_reflection()
    assert res is not None
    assert res["llm_synthesized"] is True
    assert "Kullanıcı Emir hava durumunu sordu" in res["summary"]
    brain.world_memory.observe.assert_called_once()
    brain.social_db.moments.add_or_boost.assert_called_once()

