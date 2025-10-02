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

    # Gateway app'i oluştur
    from modules.gateway.xGatewayService import create_app  # type: ignore
    from modules.gateway.config_loader import load_config  # type: ignore

    cfg = load_config()
    app = create_app()

    # Uvicorn başlat
    host = str(cfg["server"]["host"])
    port = int(cfg["server"]["port"])
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
