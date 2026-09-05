from __future__ import annotations

import threading

from modules.autonomy.services.mood import MoodManager


def _manager() -> MoodManager:
    return MoodManager({"defaults": {"mood": {"decay_rate": 0.0}}}, social_db=None)


def test_mood_snapshot_is_deep_copy():
    m = _manager()
    snap = m.snapshot()
    snap["happiness"] = 999
    snap["emotions"] = ["x"]
    assert m.state["happiness"] != 999
    assert "emotions" not in m.state


def test_mood_concurrent_modify_no_lost_updates():
    """C1 regression: N threads x M deltas must all land (no lock = lost updates)."""
    m = _manager()
    threads_n, per_thread = 8, 250
    delta = 0.02  # happiness starts at 50 -> 50+0.02*2000 = 90 (no clamp)
    barrier = threading.Barrier(threads_n)

    def worker():
        barrier.wait()
        for _ in range(per_thread):
            m.modify("happiness", delta)

    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = 50 + delta * threads_n * per_thread
    assert abs(m.state["happiness"] - expected) < 1e-6


def test_mood_update_and_modify_interleave_safely():
    m = _manager()
    errors: list[Exception] = []

    def updater():
        for _ in range(300):
            try:
                m.update()
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    def modifier():
        for _ in range(300):
            try:
                m.modify("curiosity", 0.5)
                m.satisfy_need("rest", 0.5)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    tu = threading.Thread(target=updater)
    tm = threading.Thread(target=modifier)
    tu.start(); tm.start(); tu.join(); tm.join()

    assert not errors
    for key in ("happiness", "energy", "curiosity", "fear", "anger"):
        assert 0 <= m.state[key] <= 100


def test_get_dominant_emotion_reads_consistent_snapshot():
    m = _manager()
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            m.modify("anger", 30 if i % 2 == 0 else -30)
            i += 1

    tw = threading.Thread(target=writer)
    tw.start()
    try:
        for _ in range(200):
            label = m.get_dominant_emotion()
            assert label in {
                "furious", "fear", "anger", "joy", "sadness",
                "curiosity", "tired", "neutral",
            }
    finally:
        stop.set()
        tw.join()


def test_p0_locks_present_in_sources():
    """Contract: C3/C4 locks are wired where the report requires them."""
    base = "modules/autonomy/services/"
    brain_init = open(base + "brain_init.py", encoding="utf-8").read()
    assert "_express_lock" in brain_init
    assert "_memory_write_lock" in brain_init

    emotion_sync = open(base + "brain_parts/emotion_sync.py", encoding="utf-8").read()
    assert "with self._express_lock" in emotion_sync

    decision = open(base + "brain_parts/decision.py", encoding="utf-8").read()
    assert "_memory_write_lock" in decision

    rituals = open(base + "brain_parts/scenario_rituals.py", encoding="utf-8").read()
    assert "_memory_write_lock" in rituals

    router = open("modules/autonomy/api/router.py", encoding="utf-8").read()
    assert "brain.mood.snapshot()" in router
