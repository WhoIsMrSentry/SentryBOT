"""esp_link smoke testleri."""
import pytest


def test_import():
    """Modul import edilebilir mi?"""
    from modules.esp_link import xEspLinkService
    assert xEspLinkService is not None


def test_config_loader():
    """Config yuklenebilir mi?"""
    from modules.esp_link.config_loader import load_config
    cfg = load_config()
    assert isinstance(cfg, dict)


def test_service_instantiation():
    """Service olusturulabilir mi?"""
    from modules.esp_link import xEspLinkService
    svc = xEspLinkService(config_overrides={})
    assert svc is not None


def test_router():
    """Router olusturulabilir mi?"""
    from modules.esp_link import xEspLinkService
    from modules.esp_link.api.router import get_router
    svc = xEspLinkService()
    router = get_router(svc)
    assert router is not None
    paths = [r.path for r in router.routes]
    assert "/esp/healthz" in paths
