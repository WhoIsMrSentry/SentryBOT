from __future__ import annotations

from modules.interactions.xInteractionsService import xInteractionsService


def test_smoke():
    svc = xInteractionsService()
    svc.start()
    state = svc.engine.get_state()
    assert "metrics" in state
    svc.stop()
