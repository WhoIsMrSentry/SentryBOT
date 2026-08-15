from __future__ import annotations

import inspect
import logging
import os
import signal
import sys
import threading

import uvicorn  # type: ignore


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger("run_robot")
_FORCE_EXIT_SECONDS = 4.0


def _stop_started_services(app) -> None:
    started = getattr(getattr(app, "state", None), "started", None) or {}
    for name, service in list(started.items()):
        if name in {"notifier_bot", "notifier_polling_enabled"}:
            continue
        for method_name in ("stop_stream_processing", "stop", "shutdown", "close"):
            method = getattr(service, method_name, None)
            if not callable(method):
                continue
            try:
                result = method()
                if inspect.isawaitable(result):
                    logger.debug("async shutdown skipped for %s.%s", name, method_name)
                    try:
                        result.close()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("shutdown failed for %s.%s: %s", name, method_name, exc)
            break


def main() -> None:
    from modules.common.runtime_target import assert_raspberry_pi

    target = assert_raspberry_pi()

    try:
        from modules.logwrapper import init_logging  # type: ignore

        init_logging()
    except Exception as exc:
        logger.debug("init_logging skipped: %s", exc)

    from modules.gateway.config_loader import load_config
    from modules.gateway.xGatewayService import create_app

    cfg = load_config()
    app = create_app()
    host = str(cfg["server"]["host"])
    port = int(cfg["server"]["port"])

    logger.info("SentryBOT starting on %s", target.model)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            timeout_graceful_shutdown=3,
            access_log=False,
            log_config=None,
        )
    )

    shutdown_count = 0
    force_timer: threading.Timer | None = None

    def force_exit() -> None:
        _stop_started_services(app)
        os._exit(0)

    def request_shutdown(signum: int, _frame) -> None:
        nonlocal shutdown_count, force_timer
        shutdown_count += 1
        if shutdown_count >= 2:
            force_exit()
            return
        logger.info("shutdown signal received: %s", signum)
        server.should_exit = True
        _stop_started_services(app)
        if force_timer is not None:
            force_timer.cancel()
        force_timer = threading.Timer(_FORCE_EXIT_SECONDS, force_exit)
        force_timer.daemon = True
        force_timer.start()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    try:
        server.run()
    finally:
        if force_timer is not None:
            force_timer.cancel()
        _stop_started_services(app)


if __name__ == "__main__":
    main()
