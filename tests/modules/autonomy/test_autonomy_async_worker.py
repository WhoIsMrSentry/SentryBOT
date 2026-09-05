from __future__ import annotations

import time
from modules.autonomy.services.brain import AutonomyBrain


def test_autonomy_brain_worker_executor_init_and_stop():
    cfg = {
        "llm": {"enabled": False},
        "endpoints": {},
        "defaults": {"poll_interval_s": 0.1},
    }
    brain = AutonomyBrain(cfg)
    assert brain._worker_executor is not None
    assert not brain._agentic_decision_in_progress

    brain.stop()
    # Stopping should be safe and idempotent
    brain.stop()


def test_service_client_submit_background():
    from modules.autonomy.services.client import ServiceClient

    client = ServiceClient()
    executed = []

    def task(x):
        time.sleep(0.01)
        executed.append(x)
        return x * 2

    future = client.submit_background(task, 21)
    res = future.result(timeout=2.0)
    assert res == 42
    assert executed == [21]
    client.close()
