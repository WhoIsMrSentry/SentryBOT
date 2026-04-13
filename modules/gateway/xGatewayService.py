
from __future__ import annotations
import logging
from fastapi import FastAPI
from .config_loader import load_config
from contextlib import asynccontextmanager

logger = logging.getLogger("gateway.service")

# Optional central logging
try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception as exc:
    logger.debug("global logging init skipped: %s", exc)


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bootstrap modules in startup phase so we can start async services cleanly.
        started = {}
        try:
            from .services.bootstrap import bootstrap  # type: ignore
            started = bootstrap(app, cfg)
            app.state.started = started  # make started available to runtime
        except Exception as exc:
            logger.warning("gateway bootstrap failed: %s", exc)

        # Mount core router after bootstrap so it receives the started dict reference
        try:
            from .api.router import get_router as get_core_router  # type: ignore
            app.include_router(get_core_router(cfg, app.state.started))  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("gateway core router mount failed: %s", exc)

        # Start async-only services that were exposed by bootstrap (e.g., notifier bot)
        try:
            nb = (app.state.started or {}).get("notifier_bot")
            if nb and (app.state.started or {}).get("notifier_polling_enabled"):
                try:
                    await nb.start()
                except Exception as e:
                    logger.warning("notifier start failed: %s", e)
        except Exception:
            pass

        try:
            yield
        finally:
            # Shutdown: stop async services then attempt best-effort stop/close on started services
            try:
                nb = (app.state.started or {}).get("notifier_bot")
                if nb and (app.state.started or {}).get("notifier_polling_enabled"):
                    try:
                        await nb.stop()
                    except Exception:
                        pass
            except Exception:
                pass

            for name, svc in list((app.state.started or {}).items()):
                try:
                    if name in ("notifier_bot", "notifier_polling_enabled"):
                        continue
                    if hasattr(svc, "stop") and callable(getattr(svc, "stop")):
                        try:
                            svc.stop()
                        except BaseException:
                            pass
                    elif hasattr(svc, "shutdown") and callable(getattr(svc, "shutdown")):
                        try:
                            svc.shutdown()
                        except BaseException:
                            pass
                    elif hasattr(svc, "close") and callable(getattr(svc, "close")):
                        try:
                            svc.close()
                        except BaseException:
                            pass
                except Exception:
                    pass

    app = FastAPI(title="SentryBOT Gateway", lifespan=lifespan)
    # ensure state exists as a dict reference
    app.state.started = {}  # type: ignore[attr-defined]

    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]))
