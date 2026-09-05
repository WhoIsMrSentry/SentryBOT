from __future__ import annotations

import asyncio
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
_STOPPED_SERVICE_IDS: set[int] = set()


def _run_coroutine_sync(name: str, method_name: str, coro) -> None:
    """Run an async stop() to completion when no loop is running here.

    If the uvicorn loop is still alive in this thread (signal-handler phase),
    defer to its own graceful lifespan shutdown instead of double-stopping.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    logger.debug("async shutdown deferred to lifespan for %s.%s", name, method_name)
    coro.close()


def _stop_started_services(app) -> None:
    started = getattr(getattr(app, "state", None), "started", None) or {}
    for name, service in list(started.items()):
        if name in {"notifier_bot", "notifier_polling_enabled"}:
            continue
        key = id(service)
        if key in _STOPPED_SERVICE_IDS:
            continue
        for method_name in ("stop_stream_processing", "stop", "shutdown", "close"):
            method = getattr(service, method_name, None)
            if not callable(method):
                continue
            try:
                result = method()
                if inspect.isawaitable(result):
                    _run_coroutine_sync(name, method_name, result)
            except Exception as exc:
                logger.debug("shutdown failed for %s.%s: %s", name, method_name, exc)
            finally:
                _STOPPED_SERVICE_IDS.add(key)
            break


def main() -> None:
    from modules.common.runtime_target import assert_raspberry_pi

    target = assert_raspberry_pi()

    try:
        from modules.runtime_console.logwrapper import init_logging  # type: ignore

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
        # NOTE: do not manually stop services here; uvicorn's graceful
        # shutdown runs the app lifespan (which awaits async stops) right
        # after should_exit takes effect. The timer below only guards the
        # case where graceful shutdown hangs.
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
