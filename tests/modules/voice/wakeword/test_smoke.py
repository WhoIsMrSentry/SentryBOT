from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.voice.wakeword import WakewordService
from modules.voice.wakeword.api.router import get_router


def test_wakeword_smoke_import(tmp_path):
    cfg_file = tmp_path / "wakeword.yml"
    cfg_file.write_text("enabled: false\nauto_calibrate:\n  enabled: false\n", encoding="utf-8")
    svc = WakewordService(config_path=str(cfg_file))
    assert svc is not None
    app = FastAPI()
    app.include_router(get_router(svc))
    client = TestClient(app)
    health = client.get("/wakeword/healthz")
    assert health.status_code == 200
    assert "ok" in health.json()
    st = client.get("/wakeword/status")
    assert st.status_code == 200
