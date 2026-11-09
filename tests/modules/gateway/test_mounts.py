def test_gateway_bootstrap_mounts():
    from fastapi import FastAPI
    from modules.gateway.services.bootstrap import bootstrap

    include_cfg = {
        "arduino": True,
        "vlm_bridge": True,
        "neopixel": True,
        "interactions": True,
        "speak": True,
        "speech": True,
        "wakeword": True,
        "ollama": True,
        "camera": True,
        "logs": True,
        "animate": True,
        "piservo": True,
        "autonomy": True,
        "telemetry": True,
        "diagnostics": True,
        "state_manager": True,
        "scheduler": True,
        "notifier": True,
        "runtime_console": True,
        "config_center": True,
    }

    cfg = {"include": include_cfg}
    app = FastAPI()
    started = bootstrap(app, cfg)

    expected_mounted = [
        "arduino",
        "vlm_bridge",
        "neopixel",
        "interactions",
        "speak",
        "speech",
        "wakeword",
        "ollama",
        "camera",
        "logs",
        "animate",
        "piservo",
        "autonomy",
        "telemetry",
        "diagnostics",
        "state_manager",
        "scheduler",
        "notifier",
        "runtime_console",
        "calibration",
        "config_center",
    ]

    for module_name in expected_mounted:
        assert module_name in started

    assert "ota" not in started
    assert "mutagen" not in started
    assert "admin_ui" not in started


def test_gateway_lifespan_routes_and_autonomy_contracts(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from modules.gateway.xGatewayService import create_app

    monkeypatch.setenv("SENTRYBOT_DISABLE_AUTOSTART", "true")
    minimal_cfg = {
        "server": {"host": "127.0.0.1", "port": 8080},
        "include": {
            "arduino": True,
            "state_manager": True,
            "autonomy": True,
            "diagnostics": True,
        },
        "state_manager": {"backend": "json", "path": str(tmp_path / "state.json")},
    }
    monkeypatch.setattr("modules.gateway.xGatewayService.load_config", lambda _p=None: minimal_cfg)

    app = create_app()
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert isinstance(health.json(), dict)

        ready = client.get("/readyz")
        assert ready.status_code in {200, 503}

        state_resp = client.get("/state/get")
        assert state_resp.status_code == 200

        arduino_resp = client.get("/arduino/healthz")
        assert arduino_resp.status_code == 200
        assert "ok" in arduino_resp.json()

        autonomy_resp = client.get("/autonomy/state")
        assert autonomy_resp.status_code == 200
        assert isinstance(autonomy_resp.json(), dict)
