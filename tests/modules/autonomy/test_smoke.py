"""autonomy smoke tests."""


def test_import_brain():
    from modules.autonomy.services.brain import AutonomyBrain

    assert AutonomyBrain is not None


def test_config_loader():
    from modules.autonomy.config_loader import load_config

    cfg = load_config()
    assert isinstance(cfg, dict)


def test_service_client_urls():
    from modules.autonomy.services.client import ServiceClient

    client = ServiceClient({"state_manager": "http://127.0.0.1:8080/state"})
    assert client.urls["state_manager"].endswith("/state")
