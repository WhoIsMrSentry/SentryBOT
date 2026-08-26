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
