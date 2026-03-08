from __future__ import annotations
"""
SentryBOT ana başlatıcı
- Merkezi loglama
- Gateway app oluşturma
- Uvicorn ile servis başlatma
"""
import os
import sys
import logging
import uvicorn  # type: ignore

# Proje kökünü PYTHONPATH'e ekle (script doğrudan çalıştığında)
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger("run_robot")


def main() -> None:
    # Logları erken başlat (opsiyonel hatalarda devam et)
    try:
        from modules.logwrapper import init_logging  # type: ignore
        init_logging()
    except Exception as exc:
        logger.debug("init_logging skipped: %s", exc)

    # Gateway app'i oluştur (platforms klasörü gereksiz; ana dizinden çalışır)
    from modules.gateway.xGatewayService import create_app  # type: ignore
    from modules.gateway.config_loader import load_config  # type: ignore

    # Ortam değişkeni ile konfig override desteklenir; yoksa modül varsayılanı kullanılır
    # Örn: $env:GATEWAY_CONFIG = "modules/gateway/config/config.yml"

    cfg = load_config()
    app = create_app()

    # Uvicorn başlat
    host = str(cfg["server"]["host"])
    port = int(cfg["server"]["port"])
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
