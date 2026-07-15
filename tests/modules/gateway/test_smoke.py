def test_bootstrap_import():
    from modules.gateway.services.bootstrap import bootstrap

    assert callable(bootstrap)


def test_config_loader():
    from modules.gateway.config_loader import load_config

    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "include" in cfg
