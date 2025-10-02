from fastapi.testclient import TestClient

from modules.piservo.xPiServoService import create_app


def test_healthz():
    app = create_app()
    client = TestClient(app)
    r = client.get("/piservo/healthz")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_set_angles():
    app = create_app()
    client = TestClient(app)
    r = client.post("/piservo/set", params={"left": 90, "right": 90})
    assert r.status_code == 200
    assert r.json().get("ok") is True
