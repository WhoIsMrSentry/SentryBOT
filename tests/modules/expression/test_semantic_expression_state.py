from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.expression.api.router import get_router
from modules.expression.services.state import SemanticExpressionEngine


def test_default_state_targets_are_truthful():
    eng = SemanticExpressionEngine({})
    payload = eng.get_state()
    assert payload["ok"] is True
    assert payload["state"]["emotion"] == "neutral"
    assert payload["targets"]["led"]["mode"] == "breathe"
    assert payload["targets"]["oled"]["mood"] == "neutral"


def test_manual_semantic_state_is_validated_and_mapped():
    eng = SemanticExpressionEngine({})
    out = eng.apply({"emotion": "curious", "arousal": "high", "attention": "sound"}, source="test", reason="unit")
    assert out["state"]["emotion"] == "curious"
    assert out["state"]["attention"] == "sound"
    assert out["targets"]["led"]["mode"] == "pulse"
    assert out["targets"]["pose"]["ear_gesture"] == "sound"


def test_event_mapping_updates_state_without_hardware_side_effects():
    eng = SemanticExpressionEngine({})
    out = eng.event("wakeword.detected", {"confidence": 0.9})
    assert out["state"]["emotion"] == "listening"
    assert out["state"]["listening"] is True
    assert out["targets"]["led"]["mode"] == "listen"
    out = eng.event("speak.started", {})
    assert out["state"]["speaking"] is True
    assert out["targets"]["led"]["mode"] == "listen_vu"


def test_expression_router_contract():
    eng = SemanticExpressionEngine({})
    app = FastAPI()
    app.include_router(get_router(eng))
    client = TestClient(app)
    assert client.get("/expression/status").json()["ok"] is True
    r = client.post("/expression/state", json={"emotion": "happy", "attention": "user"})
    assert r.status_code == 200
    assert r.json()["semantic"]["state"]["emotion"] == "happy"
    r = client.post("/expression/event", json={"type": "autonomy.sleep"})
    assert r.json()["semantic"]["state"]["emotion"] == "sleepy"
