from __future__ import annotations
"""
SentryBOT ana başlatıcı
- Merkezi loglama
- Gateway app oluşturma
- Uvicorn ile servis başlatma
"""
import inspect
import os
import signal
import sys
import logging
import threading
import uvicorn  # type: ignore

# Proje kökünü PYTHONPATH'e ekle (script doğrudan çalıştığında).
# Not: modules/<mod>/ alt dizinlerini sys.path'e eklemeyin; bu,
# "from modules.gateway.xGatewayService" gibi importları bozar.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger("run_robot")

_GATEWAY_SERVICE_FILE = os.path.join(ROOT, "modules", "gateway", "xGatewayService.py")
_FORCE_EXIT_SECONDS = 4.0


def _stop_started_services(app) -> None:
    started = getattr(getattr(app, "state", None), "started", None) or {}
    for name, svc in list(started.items()):
        if name in ("notifier_bot", "notifier_polling_enabled"):
            continue
        for method_name in ("stop_stream_processing", "stop", "shutdown", "close"):
            method = getattr(svc, method_name, None)
            if not callable(method):
                continue
            try:
                res = method()
                if inspect.isawaitable(res):
                    logger.debug("skip async %s on %s during sync shutdown", method_name, name)
            except Exception as exc:
                logger.debug("shutdown %s.%s failed: %s", name, method_name, exc)
            break


def main() -> None:
    # Logları erken başlat (opsiyonel hatalarda devam et)
    try:
        from modules.logwrapper import init_logging  # type: ignore
        init_logging()
    except Exception as exc:
        logger.debug("init_logging skipped: %s", exc)

    if not os.path.isfile(_GATEWAY_SERVICE_FILE):
        raise SystemExit(
            f"Missing gateway entrypoint: {_GATEWAY_SERVICE_FILE}\n"
            "Repo incomplete — on the Pi run: git fetch origin dev && git reset --hard origin/dev"
        )

    # Gateway app'i oluştur (repo kökünden çalıştırın: python run_robot.py)
    from modules.gateway.xGatewayService import create_app  # type: ignore
    from modules.gateway.config_loader import load_config  # type: ignore
    # Ayrıca autonomy konfigunu okuyup startup durumunu run_robot log'una yazalım
    try:
        from modules.autonomy.config_loader import load_config as load_autonomy_config  # type: ignore
        aut_cfg = load_autonomy_config()
    except Exception:
        aut_cfg = None

    cfg = load_config()
    app = create_app()

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
        logger.info(
            "Autonomy owner: enabled=%s require_presence=%s polite_message=%s",
            owner_cfg.get("enabled"),
            owner_cfg.get("require_presence"),
            owner_cfg.get("polite_message"),
        )

    host = str(cfg["server"]["host"])
    port = int(cfg["server"]["port"])
    uvicorn_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        timeout_graceful_shutdown=3,
    )
    server = uvicorn.Server(uvicorn_config)

    shutdown_count = 0
    force_timer: threading.Timer | None = None

    def _force_exit() -> None:
        logger.warning("Shutdown timeout — forcing exit")
        _stop_started_services(app)
        os._exit(0)

    def _request_shutdown(signum: int, _frame) -> None:
        nonlocal shutdown_count, force_timer
        shutdown_count += 1
        if shutdown_count >= 2:
            logger.warning("Second interrupt — forcing exit now")
            _force_exit()
            return
        print(f"\nShutdown signal ({signum}); stopping...", file=sys.stderr, flush=True)
        logger.info("Shutdown signal received (%s); stopping services...", signum)
        sys.stdout.flush()
        sys.stderr.flush()
        server.should_exit = True
        _stop_started_services(app)
        if force_timer is not None:
            force_timer.cancel()
        force_timer = threading.Timer(_FORCE_EXIT_SECONDS, _force_exit)
        force_timer.daemon = True
        force_timer.start()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    logger.info(
        "Press Ctrl+C once to stop (%ss max). Press twice to force quit.",
        int(_FORCE_EXIT_SECONDS),
    )
    try:
        server.run()
    finally:
        if force_timer is not None:
            force_timer.cancel()
        _stop_started_services(app)


if __name__ == "__main__":
    main()
