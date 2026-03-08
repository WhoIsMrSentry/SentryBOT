def test_gateway_bootstrap_mounts():
    from fastapi import FastAPI
    from modules.gateway.services.bootstrap import bootstrap

    include_cfg = {
        "arduino": True,
        "vision_bridge": True,
        "neopixel": True,
        "interactions": True,
        "speak": True,
        "speech": True,
        "wakeword": True,
        "ollama": True,
        "wiki_rag": True,
        "camera": True,
        "logs": True,
        "animate": True,
        "piservo": True,
        "autonomy": True,
        "hardware": True,
        "telemetry": True,
        "diagnostics": True,
        "state_manager": True,
        "scheduler": True,
        "notifier": True,
        "calibration": True,
        "config_center": True,
        "ota": False,
        "mutagen": False,
    }

    cfg = {"include": include_cfg}
    app = FastAPI()
    started = bootstrap(app, cfg)

    expected_mounted = [
        "arduino",
        "vision_bridge",
        "neopixel",
        "interactions",
        "speak",
        "speech",
        "wakeword",
        "ollama",
        "wiki_rag",
        "camera",
        "logs",
        "animate",
        "piservo",
        "autonomy",
        "hardware",
        "telemetry",
        "diagnostics",
        "state_manager",
        "scheduler",
        "notifier",
        "calibration",
        "config_center",
    ]

    for module_name in expected_mounted:
        assert module_name in started

    assert "ota" not in started
    assert "mutagen" not in started
