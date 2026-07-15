from __future__ import annotations

from modules.config_center.xConfigCenterService import create_app


def test_create_app():
    app = create_app()
    assert app is not None
