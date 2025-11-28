from __future__ import annotations
"""
SentryBOT ana başlatıcı
- Merkezi loglama
- Gateway app oluşturma
- Uvicorn ile servis başlatma
"""
import os
import sys
import uvicorn  # type: ignore
from pathlib import Path

# Proje kökünü PYTHONPATH'e ekle (script doğrudan çalıştığında)
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> None:
    # Logları erken başlat (opsiyonel hatalarda devam et)
    try:
        from modules.logwrapper import init_logging  # type: ignore
        init_logging()
    except Exception:
        pass

    # Gateway app'i oluştur (platform override destekli)
    # Platform yollarını öne al ki platforms/<plat> altındaki modules ve configs gölgelensin
    try:
        from platforms.loader import prepend_platform_paths  # type: ignore
        current_platform = prepend_platform_paths()
    except Exception:
        current_platform = None
    from modules.gateway.xGatewayService import create_app  # type: ignore
    from modules.gateway.config_loader import load_config  # type: ignore

    # Windows gibi platformlarda platforms/<plat>/configs/gateway.config.yml varsa otomatik kullan
    cfg_path = None
    try:
        root = Path(ROOT)
        if current_platform:
            plat_cfg = root / "platforms" / str(current_platform) / "configs" / "gateway.config.yml"
            if plat_cfg.exists():
                cfg_path = str(plat_cfg)
    except Exception:
        cfg_path = None

    # Ortam değişkeni ile de override edilebilir (öncelik env'de)
    if cfg_path and not os.getenv("GATEWAY_CONFIG"):
        os.environ["GATEWAY_CONFIG"] = cfg_path

    cfg = load_config()
    app = create_app()

    # Uvicorn başlat
    host = str(cfg["server"]["host"])
    port = int(cfg["server"]["port"])
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
