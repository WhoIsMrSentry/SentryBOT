def test_gateway_bootstrap_mounts():
    from fastapi import FastAPI
    from modules.gateway.services.bootstrap import bootstrap
    cfg = {"include": {"ota": True, "mutagen": True}}
    app = FastAPI()
    started = bootstrap(app, cfg)
    assert "ota" in started
    assert "mutagen" in started
