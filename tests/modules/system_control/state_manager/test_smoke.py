from __future__ import annotations

from modules.system_control.state_manager.xStateService import create_app


def test_create_app():
    app = create_app()
    assert app is not None


def test_store_notifies_operational_and_emotions():
    from modules.system_control.state_manager.services.store import StateStore

    seen: list[tuple[str, object]] = []
    store = StateStore(persistence={"type": "memory"})
    store.subscribe(lambda key, value: seen.append((key, value)))
    store.set_operational("busy")
    store.set_emotions(["happy"])
    store.update({"other": 1, "operational": "idle"})
    assert ("operational", "busy") in seen
    assert ("emotions", ["happy"]) in seen
    assert ("operational", "idle") in seen
    assert all(item[0] != "other" for item in seen)
