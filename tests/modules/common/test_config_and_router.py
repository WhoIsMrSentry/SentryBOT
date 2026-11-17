"""Unit tests for config, policy, health, and router_factory in modules.common."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.common import health as common_health
from modules.common.config_loader import inject_google_api_key, load_ai_provider_config
from modules.common.health import HealthChecker, HealthResponse
from modules.common.model_policy import ModelPolicy, get_model_policy, get_model_policy_async
from modules.common.ollama_url import (
    DEFAULT_LOCAL_OLLAMA_URL,
    DEFAULT_REMOTE_OLLAMA_URL,
    default_ollama_base_url,
    ensure_ollama_host_env,
    normalize_ollama_url,
)
from modules.common.router_factory import (
    ErrorResponse,
    FilterParams,
    RateLimitMiddleware,
    RouterConfig,
    RouterFactory,
    create_crud_router,
    create_router,
    paginated_response,
)


# ---------------------------------------------------------------------------
# ollama_url & model_policy
# ---------------------------------------------------------------------------

def test_ollama_url_constants_and_env(monkeypatch):
    assert default_ollama_base_url() == DEFAULT_LOCAL_OLLAMA_URL
    assert DEFAULT_REMOTE_OLLAMA_URL.startswith("http://")
    assert normalize_ollama_url("http://127.0.0.1:8080/ollama") == DEFAULT_LOCAL_OLLAMA_URL

    import os

    prev_env = {var: os.environ.get(var) for var in (
        "OLLAMA_HOST",
        "OLLAMA_BASE_URL",
        "SENTRYBOT_OLLAMA_BASE_URL",
        "SENTRYBOT_REMOTE_OLLAMA_URL",
        "SENTRYBOT_OLLAMA_URL",
    )}
    for var in prev_env:
        monkeypatch.delenv(var, raising=False)

    try:
        ensure_ollama_host_env()
        assert monkeypatch  # sanity

        assert os.environ["OLLAMA_HOST"] == DEFAULT_REMOTE_OLLAMA_URL
        assert os.environ["OLLAMA_BASE_URL"] == DEFAULT_REMOTE_OLLAMA_URL
    finally:
        for var, orig in prev_env.items():
            if orig is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = orig


def test_model_policy_async_and_custom_mode(monkeypatch):
    assert get_model_policy() is asyncio.run(get_model_policy_async())

    monkeypatch.delenv("SENTRYBOT_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("SENTRYBOT_REMOTE_OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("AGENT_OLLAMA_BASE_URL", raising=False)

    policy = ModelPolicy()
    policy.set_required_model("qwen3.5:9b")
    policy.set_strict_single_model(False)

    cfg = {
        "llm": {"model": "qwen3.5:14b", "temperature": 0.2},
        "agent": {"ollama_base_url": "http://127.0.0.1:8080/ollama"},
        "ollama": {"base_url": "http://10.0.0.2:11434"},
    }
    resolved = policy.resolve_model(cfg)
    assert resolved["model"] == "qwen3.5:14b"
    assert resolved["enforced"] is False

    provider_cfg = policy.get_provider_config(cfg)
    assert provider_cfg["base_url"] == "http://10.0.0.2:11434"
    assert provider_cfg["model"] == "qwen3.5:14b"


# ---------------------------------------------------------------------------
# config_loader.load_ai_provider_config
# ---------------------------------------------------------------------------

def test_load_ai_provider_config_accepts_ai_provider_and_single_model_mode(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    cfg_file = tmp_path / "agent.yaml"
    cfg_file.write_text(
        """
agent:
  model: custom-model:7b
  ollama_base_url: "http://127.0.0.1:11434"
llm:
  provider: ollama
  single_model_mode: false
  model: custom-model:7b
ollama:
  base_url: "http://127.0.0.1:11434"
  model: custom-model:7b
ai_provider:
  server:
    host: 127.0.0.1
    port: 8199
""".strip(),
        encoding="utf-8",
    )

    cfg = load_ai_provider_config(str(cfg_file))
    assert cfg["llm"]["single_model_mode"] is False
    assert cfg["llm"]["model"] == "custom-model:7b"
    assert cfg["ollama"]["model"] == "custom-model:7b"
    assert int(cfg["server"]["port"]) == 8199


def test_inject_google_api_key_preserves_clean_cfg(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = inject_google_api_key({"llm": {"provider": "google_ai_studio"}})
    assert out["llm"]["provider"] == "google_ai_studio"


# ---------------------------------------------------------------------------
# health & router_factory
# ---------------------------------------------------------------------------

def test_health_response_ok_and_no_unused_helpers():
    assert "check_database" not in common_health.__all__
    assert "check_redis" not in common_health.__all__
    assert not hasattr(common_health, "check_database")
    assert not hasattr(common_health, "check_redis")

    h_ok = HealthResponse.healthy()
    h_bad = HealthResponse.unhealthy()
    assert h_ok.ok is True
    assert h_bad.ok is False

    checker = HealthChecker("common_test", version="2.0.0")
    checker.add_check("quick", lambda: {"status": "healthy"})
    r1 = checker.run()
    r2 = checker.run()
    assert r1["status"] == "healthy"
    assert r2["version"] == "2.0.0"
    assert r2["checks"]["quick"]["status"] == "healthy"
    res = checker.get_health_response()
    assert res.ok is True
    assert res.checks["quick"]["status"] == "healthy"


def test_router_factory_pydantic_models_build_crud_and_ratelimit():
    e1 = ErrorResponse(error="a")
    e2 = ErrorResponse(error="b")
    e1.details["x"] = 1
    assert e2.details == {}

    f1 = FilterParams()
    f2 = FilterParams()
    f1.filters["k"] = "v"
    assert f2.filters == {}

    page_resp = paginated_response([1, 2], total=2, page=1, page_size=0)
    assert page_resp.status_code == 200

    factory = RouterFactory(RouterConfig(service_name="svc", prefix="/api", include_version=True))
    factory.set_health_check(lambda: {"status": "healthy", "service": "svc"})
    factory.add_route("/old", "GET", lambda: {"legacy": True}, deprecated=True)

    app = FastAPI()
    app.middleware("http")(RateLimitMiddleware(max_requests=2, window_seconds=60))
    app.include_router(factory.build())

    crud_router = create_crud_router(
        service_name="items",
        prefix="/items-api",
        list_handler=lambda: [],
        health_check_fn=lambda: {"status": "healthy", "service": "items"},
    )
    app.include_router(crud_router)

    extra_router = create_router(
        service_name="extra",
        prefix="/extra",
        include_version=False,
        routes=[{"path": "/ping", "method": "GET", "handler": lambda: {"pong": True}}],
    )
    app.include_router(extra_router)

    client = TestClient(app)
    r1 = client.get("/api/healthz")
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    r2 = client.get("/extra/ping")
    assert r2.status_code == 200
    assert r2.json() == {"pong": True}

    # 3rd request hits RateLimitMiddleware (max_requests=2)
    r3 = client.get("/api/old")
    assert r3.status_code == 429
    assert r3.json()["error_code"] == "RATE_LIMITED"
