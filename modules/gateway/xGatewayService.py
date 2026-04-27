
from __future__ import annotations
import inspect
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .config_loader import load_config
from contextlib import asynccontextmanager

logger = logging.getLogger("gateway.service")

# Optional central logging
try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception as exc:
    logger.debug("global logging init skipped: %s", exc)


def _listify(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _build_security_policy(cfg: dict) -> dict:
    sec = cfg.get("security", {}) if isinstance(cfg.get("security", {}), dict) else {}
    api_keys = set(_listify(sec.get("api_keys", [])))
    admin_keys = set(_listify(sec.get("admin_keys", [])))
    valid_keys = set(api_keys) | set(admin_keys)
    return {
        "enabled": bool(sec.get("enabled", False)),
        "api_key_header": str(sec.get("api_key_header", "X-API-Key")),
        "role_header": str(sec.get("role_header", "X-Role")),
        "exempt_prefixes": _listify(
            sec.get(
                "exempt_prefixes",
                ["/docs", "/redoc", "/openapi.json", "/health", "/healthz", "/status"],
            )
        ),
        "admin_write_prefixes": _listify(
            sec.get("admin_write_prefixes", ["/config", "/ota", "/scheduler/jobs"])
        ),
        "admin_keys": admin_keys,
        "valid_keys": valid_keys,
    }


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    security = _build_security_policy(cfg)

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
                            res = svc.stop()
                            if inspect.isawaitable(res):
                                await res
                        except BaseException:
                            pass
                    elif hasattr(svc, "shutdown") and callable(getattr(svc, "shutdown")):
                        try:
                            res = svc.shutdown()
                            if inspect.isawaitable(res):
                                await res
                        except BaseException:
                            pass
                    elif hasattr(svc, "close") and callable(getattr(svc, "close")):
                        try:
                            res = svc.close()
                            if inspect.isawaitable(res):
                                await res
                        except BaseException:
                            pass
                except Exception:
                    pass

    app = FastAPI(title="SentryBOT Gateway", lifespan=lifespan)
    # ensure state exists as a dict reference
    app.state.started = {}  # type: ignore[attr-defined]

    if security.get("enabled", False):
        @app.middleware("http")
        async def _security_middleware(request, call_next):
            path = str(request.url.path or "")
            method = str(request.method or "GET").upper()

            if method == "OPTIONS":
                return await call_next(request)

            for prefix in security["exempt_prefixes"]:
                if path.startswith(prefix):
                    return await call_next(request)

            # Read-only access is left open by default; write operations require key.
            if method in {"GET", "HEAD"}:
                return await call_next(request)

            key = request.headers.get(security["api_key_header"]) or request.query_params.get("api_key")
            if not key or str(key) not in security["valid_keys"]:
                return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})

            needs_admin = any(path.startswith(prefix) for prefix in security["admin_write_prefixes"])
            if needs_admin:
                header_role = str(request.headers.get(security["role_header"], "")).strip().lower()
                is_admin = str(key) in security["admin_keys"] or header_role == "admin"
                if not is_admin:
                    return JSONResponse(status_code=403, content={"ok": False, "error": "admin_required"})

            return await call_next(request)

    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]), log_config=None)
