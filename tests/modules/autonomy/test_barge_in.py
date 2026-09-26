"""Natural barge-in policy."""

from __future__ import annotations

from modules.autonomy.services.barge_in import BargeInController
from modules.autonomy.services.brain_parts.vocal import VocalMixin


def test_meaningful_speech_interrupts_while_robot_talking():
    bc = BargeInController({"min_words": 2, "cooldown_s": 0.0})
    assert bc.should_interrupt(robot_speaking=True, user_text="dur bir saniye", now=100.0) is True


def test_no_interrupt_when_robot_silent():
    bc = BargeInController({"min_words": 2})
    assert bc.should_interrupt(robot_speaking=False, user_text="dur bir saniye", now=100.0) is False


def test_single_word_does_not_interrupt_without_wakeword():
    bc = BargeInController({"min_words": 2})
    assert bc.should_interrupt(robot_speaking=True, user_text="ee", now=100.0) is False


def test_laya_urgent_single_word_interrupts_without_wakeword():
    bc = BargeInController({"min_words": 4, "cooldown_s": 0.0})
    assert bc.should_interrupt(
        robot_speaking=True,
        user_text="Dur!",
        urgent=True,
        now=100.0,
    ) is True


def test_wakeword_interrupts_even_if_single_word():
    bc = BargeInController({"min_words": 5})
    assert bc.should_interrupt(robot_speaking=True, user_text="sentry", has_wakeword=True, now=100.0) is True


def test_cooldown_blocks_rapid_reinterrupt():
    bc = BargeInController({"min_words": 1, "cooldown_s": 2.0})
    assert bc.should_interrupt(robot_speaking=True, user_text="dur", now=100.0) is True
    # within cooldown -> blocked
    assert bc.should_interrupt(robot_speaking=True, user_text="dur", now=101.0) is False
    # after cooldown -> allowed
    assert bc.should_interrupt(robot_speaking=True, user_text="dur", now=103.0) is True


def test_disabled_never_interrupts():
    bc = BargeInController({"enabled": False})
    assert bc.should_interrupt(robot_speaking=True, user_text="dur bir saniye", has_wakeword=True, now=100.0) is False


def test_laya_emergency_reaches_brain_barge_in_controller():
    class _Brain(VocalMixin):
        def __init__(self):
            self.laya_engine = type("Laya", (), {
                "_is_available": True,
                "decide": lambda _self, _text: "emergency-decision",
                "is_emergency_decision": lambda _self, decision: decision == "emergency-decision",
            })()
            self.barge_in = BargeInController({"cooldown_s": 0.0})
            self.stopped = False

        def _robot_is_speaking(self):
            return True

        def _barge_in_stop_speaking(self):
            self.stopped = True

    brain = _Brain()

    handled = brain._handle_barge_in_and_wakeword("Dur!", "dur!", False, "req-1")

    assert not handled
    assert brain.stopped
