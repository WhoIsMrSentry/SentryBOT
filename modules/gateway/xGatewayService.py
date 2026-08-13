from __future__ import annotations

import inspect
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config_loader import load_config

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


def _client_is_loopback(request) -> bool:
    try:
        host = str(getattr(request.client, "host", "") or "").strip().lower()
    except Exception:
        return False
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _root_agent_security_cfg() -> dict:
    try:
        from modules.config_center.agent_yaml_loader import load_agent_config  # type: ignore

        loaded = load_agent_config(None)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _check_insecure_defaults(cfg: dict) -> list[str]:
    """Check for insecure default credentials and return list of warnings."""
    warnings = []
    root_cfg = _root_agent_security_cfg()
    
    # Check agent.yaml auth_token
    local_agent_cfg = cfg.get("agent")
    agent_cfg = local_agent_cfg if isinstance(local_agent_cfg, dict) and local_agent_cfg else root_cfg.get("agent", {})
    agent_cfg = agent_cfg if isinstance(agent_cfg, dict) else {}
    auth_token = str(agent_cfg.get("auth_token", "") or "").strip()
    if auth_token in ("", "changeme", "your-auth-token", "replace_me"):
        warnings.append("SECURITY WARNING: agent.auth_token is using default/empty value 'changeme' - please set a strong token in config/agent.yaml")
    
    # Check esp_link WiFi password
    esp_cfg = cfg.get("esp_link", {}) if isinstance(cfg.get("esp_link", {}), dict) else {}
    network_cfg = esp_cfg.get("network", {}) if isinstance(esp_cfg.get("network", {}), dict) else {}
    wifi_password = str(network_cfg.get("password", "") or "").strip()
    wifi_ssid = str(network_cfg.get("ssid", "") or "").strip()
    if wifi_password and wifi_password == wifi_ssid and wifi_ssid == "SentryBOT":
        warnings.append("SECURITY WARNING: esp_link WiFi password equals SSID ('SentryBOT') - please set a strong unique password in modules/esp_link/config/config.yml")
    
    # Check vlm_bridge auth_token
    local_vlm_cfg = cfg.get("vlm_bridge")
    vlm_cfg = local_vlm_cfg if isinstance(local_vlm_cfg, dict) and local_vlm_cfg else root_cfg.get("vlm_bridge", {})
    vlm_cfg = vlm_cfg if isinstance(vlm_cfg, dict) else {}
    remote_cfg = vlm_cfg.get("remote", {}) if isinstance(vlm_cfg.get("remote", {}), dict) else {}
    vlm_auth = str(remote_cfg.get("auth_token", "") or "").strip()
    if vlm_auth in ("", "changeme", "your-auth-token", "replace_me"):
        warnings.append("SECURITY WARNING: vlm_bridge.remote.auth_token is using default/empty value 'changeme' - please set a strong token in config/agent.yaml")
    
    # Check gateway api_keys
    sec = cfg.get("security", {}) if isinstance(cfg.get("security", {}), dict) else {}
    api_keys = sec.get("api_keys", [])
    if not api_keys and sec.get("enabled", False):
        warnings.append("SECURITY WARNING: gateway security.enabled=true but no api_keys configured - API will reject all non-loopback requests")
    
    return warnings


def _build_security_policy(cfg: dict) -> dict:
    sec = cfg.get("security", {}) if isinstance(cfg.get("security", {}), dict) else {}
    api_keys = set(_listify(sec.get("api_keys", [])))
    admin_keys = set(_listify(sec.get("admin_keys", [])))
    env_key = str(os.environ.get("SENTRY_API_KEY", "") or "").strip()
    if env_key:
        api_keys.add(env_key)
    valid_keys = set(api_keys) | set(admin_keys)
    return {
        "enabled": bool(sec.get("enabled", False)),
        "trust_loopback": bool(sec.get("trust_loopback", True)),
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
        # Sensitive read endpoints (camera stream, last-heard speech, internal
        # state/mood, telemetry, VLM context, agent/autonomy/social state) that
        # must require a valid API key even though GET/HEAD is open by default.
        "protected_get_prefixes": _listify(
            sec.get(
                "protected_get_prefixes",
                [
                    "/camera",
                    "/speech/last",
                    "/speech/direction",
                    "/speech/track",
                    "/state",
                    "/telemetry",
                    "/vlm",
                    "/agent",
                    "/autonomy",
                    "/social",
                ],
            )
        ),
        "admin_keys": admin_keys,
        "valid_keys": valid_keys,
    }


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    security = _build_security_policy(cfg)
    
    # Check for insecure defaults at startup
    for warning in _check_insecure_defaults(cfg):
        logger.warning(warning)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bootstrap modules in startup phase so we can start async services cleanly.
        started = {}
        try:
            from .services.bootstrap import bootstrap  # type: ignore

            started = bootstrap(app, cfg)
            app.state.started = started  # make started available to runtime
            started["_startup_health"] = {"ok": True, "stage": "ready", "started_services": sorted(k for k in started if not k.startswith("_"))}
            app.state.startup_health = started["_startup_health"]  # type: ignore[attr-defined]
        except Exception as exc:
            health = {"ok": False, "stage": "bootstrap", "error": str(exc)}
            app.state.startup_health = health  # type: ignore[attr-defined]
            app.state.started["_startup_health"] = health  # type: ignore[attr-defined]
            logger.exception("gateway bootstrap failed; health will report degraded state")

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
                    elif hasattr(svc, "shutdown") and callable(
                        getattr(svc, "shutdown")
                    ):
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

            is_read_only = method in {"GET", "HEAD"}
            is_protected_read = is_read_only and any(
                path.startswith(prefix) for prefix in security["protected_get_prefixes"]
            )

            # Read-only access is left open by default; write operations and
            # the sensitive read endpoints in protected_get_prefixes (camera,
            # speech, state, telemetry, vlm, agent, autonomy, social...) are
            # subject to the same key check as writes below.
            if is_read_only and not is_protected_read:
                return await call_next(request)

            if security.get("trust_loopback", True) and _client_is_loopback(request):
                return await call_next(request)

            key = request.headers.get(
                security["api_key_header"]
            ) or request.query_params.get("api_key")
            if not key or str(key) not in security["valid_keys"]:
                return JSONResponse(
                    status_code=401, content={"ok": False, "error": "unauthorized"}
                )

            needs_admin = any(
                path.startswith(prefix) for prefix in security["admin_write_prefixes"]
            )
            if needs_admin:
                header_role = (
                    str(request.headers.get(security["role_header"], ""))
                    .strip()
                    .lower()
                )
                is_admin = str(key) in security["admin_keys"] or header_role == "admin"
                if not is_admin:
                    return JSONResponse(
                        status_code=403,
                        content={"ok": False, "error": "admin_required"},
                    )

            return await call_next(request)

    return app


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(),
        host=str(cfg["server"]["host"]),
        port=int(cfg["server"]["port"]),
        log_config=None,
    )
