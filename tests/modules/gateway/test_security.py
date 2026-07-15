"""Security middleware coverage for xGatewayService.

These tests build the real app via ``create_app`` (so the actual
``_security_middleware`` closure and ``_build_security_policy`` logic run),
but avoid triggering the FastAPI ``lifespan`` (bootstrap of every hardware
module). Starlette's ``TestClient`` only runs lifespan startup/shutdown when
used as a context manager (``with TestClient(app) as c:``); plain
``TestClient(app).get(...)`` calls never enter the lifespan, so bootstrap
never runs. We add small probe routes directly to the returned app so we can
assert on status codes without depending on any real module being mounted.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import modules.gateway.xGatewayService as gw_service

_EXEMPT_PREFIXES = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/healthz",
    "/status",
]
_ADMIN_WRITE_PREFIXES = ["/config", "/ota", "/scheduler/jobs"]
_PROTECTED_GET_PREFIXES = [
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
]

_API_KEY = "unit-test-secret-key"
_ADMIN_KEY = "unit-test-admin-key"

# A non-loopback, documentation-only (TEST-NET-3, RFC 5737) address used to
# simulate a client that is *not* on localhost.
_REMOTE_ADDR = ("203.0.113.10", 51000)
_LOOPBACK_ADDR = ("127.0.0.1", 51000)


def _security_config(**overrides) -> dict:
    sec = {
        "enabled": True,
        "trust_loopback": True,
        "api_key_header": "X-API-Key",
        "role_header": "X-Role",
        "api_keys": [_API_KEY],
        "admin_keys": [_ADMIN_KEY],
        "exempt_prefixes": list(_EXEMPT_PREFIXES),
        "admin_write_prefixes": list(_ADMIN_WRITE_PREFIXES),
        "protected_get_prefixes": list(_PROTECTED_GET_PREFIXES),
    }
    sec.update(overrides)
    return sec


def _build_app(monkeypatch, **security_overrides):
    monkeypatch.delenv("SENTRY_API_KEY", raising=False)
    cfg = {
        "server": {"host": "127.0.0.1", "port": 0},
        "include": {},
        "security": _security_config(**security_overrides),
    }
    monkeypatch.setattr(gw_service, "load_config", lambda config_path=None: cfg)
    app = gw_service.create_app()

    # Lightweight probe routes; the real ones are mounted during bootstrap
    # (lifespan), which is intentionally not triggered by these tests.
    @app.get("/health")
    def _health():
        return {"ok": True}

    @app.get("/camera/video")
    def _camera_video():
        return {"ok": True}

    @app.get("/speech/last")
    def _speech_last():
        return {"ok": True}

    @app.get("/telemetry/metrics")
    def _telemetry_metrics():
        return {"ok": True}

    @app.get("/vlm/results/latest")
    def _vlm_latest():
        return {"ok": True}

    @app.get("/foo/open")
    def _open_get():
        return {"ok": True}

    @app.post("/autonomy/interaction")
    def _autonomy_write():
        return {"ok": True}

    @app.post("/config/reload")
    def _config_write():
        return {"ok": True}

    return app


# (a) exempt prefix stays open without a key -----------------------------------
def test_exempt_prefix_allows_get_without_key(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.get("/health")
    assert resp.status_code == 200


# (b) protected prefix + no key + non-loopback -> 401 --------------------------
def test_protected_get_without_key_from_non_loopback_is_unauthorized(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.get("/camera/video")
    assert resp.status_code == 401

    resp2 = client.get("/speech/last")
    assert resp2.status_code == 401


# (c) protected prefix from loopback (trust_loopback=true) without key -> 200 --
def test_protected_get_from_loopback_without_key_is_allowed_when_trusted(monkeypatch):
    app = _build_app(monkeypatch, trust_loopback=True)
    client = TestClient(app, client=_LOOPBACK_ADDR)
    resp = client.get("/camera/video")
    assert resp.status_code == 200


def test_protected_get_from_loopback_without_key_is_rejected_when_not_trusted(
    monkeypatch,
):
    app = _build_app(monkeypatch, trust_loopback=False)
    client = TestClient(app, client=_LOOPBACK_ADDR)
    resp = client.get("/camera/video")
    assert resp.status_code == 401


# (d) protected prefix with a correct key -> 200 --------------------------------
def test_protected_get_with_valid_key_is_allowed(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.get("/telemetry/metrics", headers={"X-API-Key": _API_KEY})
    assert resp.status_code == 200


def test_protected_get_with_invalid_key_is_unauthorized(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.get("/vlm/results/latest", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


# Backward compatibility: GET prefixes not in protected_get_prefixes stay open -
def test_unlisted_get_prefix_remains_open_for_backward_compat(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.get("/foo/open")
    assert resp.status_code == 200


# (e) existing write-protection (POST) behavior is unaffected -------------------
def test_write_request_without_key_still_requires_auth(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.post("/autonomy/interaction")
    assert resp.status_code == 401


def test_write_request_with_valid_key_still_allowed(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.post("/autonomy/interaction", headers={"X-API-Key": _API_KEY})
    assert resp.status_code == 200


def test_admin_write_prefix_still_requires_admin_key(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    # A regular (non-admin) API key must not be enough for admin_write_prefixes.
    resp = client.post("/config/reload", headers={"X-API-Key": _API_KEY})
    assert resp.status_code == 403
    # The admin key must still work.
    resp2 = client.post("/config/reload", headers={"X-API-Key": _ADMIN_KEY})
    assert resp2.status_code == 200


def test_options_request_always_bypasses_security(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app, client=_REMOTE_ADDR)
    resp = client.options("/camera/video")
    assert resp.status_code != 401
