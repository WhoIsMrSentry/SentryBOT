def test_imports():
    import modules.ota  # noqa: F401
    from modules.ota.api import get_router  # noqa: F401
    from modules.ota.config_loader import load_config  # noqa: F401
    from modules.ota.services.uploader import OTAService  # noqa: F401


def test_router_create():
    from modules.ota.api import get_router
    r = get_router({"ota": {}})
    assert r is not None
