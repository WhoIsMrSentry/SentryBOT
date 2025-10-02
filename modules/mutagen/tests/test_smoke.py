def test_imports():
    import modules.mutagen  # noqa: F401
    from modules.mutagen.api import get_router  # noqa: F401
    from modules.mutagen.config_loader import load_config  # noqa: F401
    from modules.mutagen.services.runner import MutagenRunner  # noqa: F401


def test_router_create():
    from modules.mutagen.api import get_router
    r = get_router({"mutagen": {}})
    assert r is not None
