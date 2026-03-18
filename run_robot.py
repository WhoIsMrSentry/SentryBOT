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
    # Ayrıca autonomy konfigunu okuyup startup durumunu run_robot log'una yazalım
    try:
        from modules.autonomy.config_loader import load_config as load_autonomy_config  # type: ignore
        aut_cfg = load_autonomy_config()
    except Exception:
        aut_cfg = None

    # Ortam değişkeni ile konfig override desteklenir; yoksa modül varsayılanı kullanılır
    # Örn: $env:GATEWAY_CONFIG = "modules/gateway/config/config.yml"

    cfg = load_config()
    app = create_app()

    # Kısa durum özetini run_robot logger'ına yaz
    try:
        logger.info("Loaded gateway config: host=%s port=%s", cfg["server"]["host"], cfg["server"]["port"])
    except Exception:
        logger.info("Loaded gateway config")

    try:
        modules_dir = os.path.join(ROOT, "modules")
        modules_list = sorted([d for d in os.listdir(modules_dir) if os.path.isdir(os.path.join(modules_dir, d))])
        logger.info("Available modules: %s", ", ".join(modules_list))
    except Exception:
        logger.debug("Could not list modules directory")

    if aut_cfg:
        owner_cfg = aut_cfg.get("owner", {})
        logger.info("Autonomy owner: enabled=%s require_presence=%s polite_message=%s", owner_cfg.get("enabled"), owner_cfg.get("require_presence"), owner_cfg.get("polite_message"))

    # Uvicorn başlat
    host = str(cfg["server"]["host"])
    port = int(cfg["server"]["port"])
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
