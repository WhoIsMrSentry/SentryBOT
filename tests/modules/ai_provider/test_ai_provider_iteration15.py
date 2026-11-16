from __future__ import annotations

import json
from pathlib import Path
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests

from modules.ai_provider.api import router as router_mod
from modules.ai_provider.api.chat_routes import get_chat_router
from modules.ai_provider.api.health import get_health_router
from modules.ai_provider.api.persona_routes import get_persona_router
from modules.ai_provider.config_loader import load_config
from modules.ai_provider.models.sentry_schema import SentryResponse
from modules.ai_provider.services.chat import OllamaChatService
from modules.ai_provider.services.clients import (
    CircuitOpenError,
    OllamaClient,
    PriorityInferenceLock,
)
from modules.ai_provider.services.google_ai_client import GoogleAIStudioClient
from modules.ai_provider.services.tags import extract_llm_tags
from modules.ai_provider.services.translator import OllamaTranslator


def test_priority_inference_lock_concurrent_equal_and_ordered_priorities() -> None:
    lock = PriorityInferenceLock()
    order: list[str] = []
    ready = threading.Barrier(4)
    holder_entered = threading.Event()
    release_holder = threading.Event()

    def _holder() -> None:
        with lock.acquire(priority=1):
            holder_entered.set()
            release_holder.wait(timeout=2.0)

    def _waiter(label: str, prio: int) -> None:
        assert holder_entered.wait(timeout=2.0)
        ready.wait(timeout=2.0)
        with lock.acquire(priority=prio):
            order.append(label)

    t0 = threading.Thread(target=_holder, daemon=True)
    t0.start()
    threads = [
        threading.Thread(target=_waiter, args=("low_2a", 2), daemon=True),
        threading.Thread(target=_waiter, args=("low_2b", 2), daemon=True),
        threading.Thread(target=_waiter, args=("high_0", 0), daemon=True),
        threading.Thread(target=_waiter, args=("mid_1", 1), daemon=True),
    ]
    for t in threads:
        t.start()
    time.sleep(0.08)
    release_holder.set()
    t0.join(timeout=2.0)
    for t in threads:
        t.join(timeout=2.0)

    assert len(order) == 4
    assert order[0] == "high_0"
    assert order[1] == "mid_1"
    assert set(order[2:]) == {"low_2a", "low_2b"}


def test_ollama_client_single_http_session_circuit_breaker_and_stream(monkeypatch) -> None:
    client = OllamaClient(
        "http://127.0.0.1:11434",
        "qwen3.5:9b",
        request_timeout=3.0,
        cb_failure_threshold=2,
        cb_recovery_timeout_s=10.0,
    )
    calls = {"n": 0}

    def _fail_post(*_a, **_kw):
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(client._session, "post", _fail_post)
    monkeypatch.setattr("modules.ai_provider.services.clients.time.sleep", lambda _s: None)

    for _ in range(2):
        with pytest.raises(requests.exceptions.ConnectionError):
            client.chat([{"role": "user", "content": "hi"}])

    assert calls["n"] == 4  # 2 chat cycles x 2 retry attempts
    assert client.circuit_state()["state"] == "open"

    # Fast-fail when breaker is open: zero network calls
    with pytest.raises(CircuitOpenError):
        client.chat([{"role": "user", "content": "hi"}])
    assert calls["n"] == 4

    # Recover and test NDJSON streaming (Feature L42)
    client._breaker.record_success()

    class _StreamResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            yield json.dumps({"message": {"content": "Mer"}, "done": False})
            yield json.dumps({"message": {"content": "haba!"}, "done": True})

    captured_payloads = []

    def _ok_post(url, json=None, timeout=None, stream=False):
        captured_payloads.append((url, json, timeout, stream))
        return _StreamResp()

    monkeypatch.setattr(client._session, "post", _ok_post)
    chunks = list(client.chat_stream([{"role": "user", "content": "selam"}], priority=0))
    assert "".join(c["delta"] for c in chunks) == "Merhaba!"
    assert chunks[-1]["done"] is True
    assert captured_payloads[0][1]["think"] is False
    assert captured_payloads[0][1]["stream"] is True
    assert captured_payloads[0][2] == 3.0


def test_disabled_google_rejected_and_allowed_models_yaml(tmp_path: Path, monkeypatch) -> None:
    # Health endpoint must NOT claim ok=True for disabled non-ollama provider
    app_h = FastAPI()
    app_h.include_router(get_health_router({}, provider="google_ai_studio", model="gemini-1.5-flash"), prefix="/ollama")
    res_h = TestClient(app_h).get("/ollama/healthz").json()
    assert res_h["ok"] is False
    assert res_h["error"] == "provider_disabled"

    # ProviderDisabledError in chat returns clean ok=False JSON without 500
    gclient = GoogleAIStudioClient(api_key="AIza-test", model="gemini-1.5-flash")
    assert getattr(gclient, "DISABLED", False) is True
    svc = OllamaChatService(gclient, use_persona_as_model=False)
    app_c = FastAPI()

    class _NoTrans:
        BRIDGE_LANG = "en"

        class cfg:
            enabled = False
            default_source_lang = "tr"

        def normalize_lang(self, v, fallback="tr"):
            return v or fallback

        def detect_language(self, q):
            return "tr"

        def to_bridge(self, q, s):
            return q

        def from_bridge(self, a, t):
            return a

    app_c.include_router(get_chat_router(svc, _NoTrans(), "gemini", "google_ai_studio", "sentry", "", 1.0, False), prefix="/ollama")
    res_c = TestClient(app_c).post("/ollama/chat", params={"query": "selam"})
    assert res_c.status_code == 200
    assert res_c.json()["ok"] is False
    assert res_c.json()["error"] == "provider_disabled"

    # Router falls back cleanly when google_ai_studio disabled stub is configured + resolves @gateway actions
    cfg_file = tmp_path / "agent.yaml"
    cfg_file.write_text(
        """
agent:
  model: qwen3.5:14b
  ollama_base_url: "http://127.0.0.1:11434"
llm:
  provider: ollama
  single_model_mode: false
  allowed_models: ["qwen3.5:9b", "qwen3.5:14b"]
ollama:
  base_url: "http://127.0.0.1:11434"
  model: qwen3.5:14b
ai_provider:
  actions:
    endpoint: "@gateway/autonomy/apply_actions"
    default_apply: true
    timeout: 1.0
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("SENTRY_GATEWAY_URL", "http://127.0.0.1:9088")
    loaded = load_config(str(cfg_file))
    assert loaded["ollama"]["model"] == "qwen3.5:14b"
    assert loaded["actions"]["endpoint"] == "http://127.0.0.1:9088/autonomy/apply_actions"

    app_r = FastAPI()
    app_r.include_router(
        router_mod.get_router(
            {
                "llm": {"provider": "google_ai_studio", "single_model_mode": True},
                "google_ai_studio": {"api_key": "AIza-valid-test", "model": "gemini-1.5-flash"},
                "ollama": {"base_url": "http://127.0.0.1:11434", "model": "qwen3.5:9b"},
                "persona": {"default": "sentry", "dir": "modules/ai_provider/config/personalities"},
            }
        )
    )
    hc = TestClient(app_r).get("/ollama/healthz").json()
    assert hc["provider"] == "ollama"


def test_models_persona_structured_stream_and_gateway_actions(tmp_path: Path, monkeypatch) -> None:
    pdir = tmp_path / "personalities"
    (pdir / "sentry").mkdir(parents=True)
    (pdir / "sentry" / "persona.txt").write_text("You are Sentry.", encoding="utf-8")
    (pdir / "glados").mkdir(parents=True)
    (pdir / "glados" / "persona.txt").write_text("You are GLaDOS.", encoding="utf-8")

    class _FakeLLM:
        def __init__(self) -> None:
            self.model = "qwen3.5:9b"
            self.pulled: list[str] = []
            self.formats: list[object] = []

        def list_models(self):
            return ["qwen3.5:9b", "qwen3.5:14b"]

        def pull_model(self, name: str) -> bool:
            self.pulled.append(name)
            return True

        def create_model(self, name: str, modelfile: str) -> bool:
            return True

        def chat(self, messages, format=None, *, options=None, model=None):
            self.formats.append(format)
            if format is not None:
                return {
                    "message": {
                        "content": json.dumps(
                            {
                                "text": "Merhaba efendim.",
                                "thoughts": "Kullanim kontrolu",
                                "actions": [{"type": "servo", "attrs": {"pan": 95}}],
                            }
                        )
                    }
                }
            return {"message": {"content": "Hazirim [cmd:wave] [[servo pan=90]]"}}

        def chat_stream(self, messages, format=None, *, options=None, model=None):
            yield {"delta": "Merhaba ", "done": False}
            yield {"delta": "dunya!", "done": True}

    fake = _FakeLLM()
    monkeypatch.setattr(router_mod, "create_llm_client", lambda _cfg: (fake, "ollama"))

    posted_actions = []
    monkeypatch.setenv("SENTRY_GATEWAY_URL", "http://127.0.0.1:9911")
    monkeypatch.setattr(
        "modules.ai_provider.api.chat_routes._post_action_json",
        lambda url, payload, timeout: posted_actions.append((url, payload, timeout)),
    )

    app = FastAPI()
    app.include_router(
        router_mod.get_router(
            {
                "llm": {"provider": "ollama", "single_model_mode": True},
                "ollama": {"base_url": "http://127.0.0.1:11434", "model": "qwen3.5:9b"},
                "persona": {"default": "sentry", "dir": str(pdir)},
                "actions": {"endpoint": "@gateway/autonomy/apply_actions", "default_apply": True, "timeout": 1.2},
                "translation": {"enabled": False, "default_source_lang": "tr"},
            }
        )
    )
    client = TestClient(app)

    # Structured output (SentryResponse schema) + action forwarding
    r_struct = client.post("/ollama/chat", params={"query": "selam", "structured": True})
    assert r_struct.status_code == 200
    body = r_struct.json()
    assert body["answer"] == "Merhaba efendim."
    assert body["thoughts"] == "Kullanim kontrolu"
    assert fake.formats[-1] == SentryResponse.model_json_schema()
    assert posted_actions[0][0] == "http://127.0.0.1:9911/autonomy/apply_actions"

    # SSE stream response (Feature L42)
    r_stream = client.post("/ollama/chat", params={"query": "akis", "stream": True})
    assert r_stream.status_code == 200
    assert "text/event-stream" in r_stream.headers.get("content-type", "")
    assert "Merhaba " in r_stream.text and '"done": true' in r_stream.text

    # Runtime model switch propagates to /models & /chat
    r_add = client.post("/ollama/model/add", params={"name": "qwen3.5:14b", "set_default": True})
    assert r_add.status_code == 200 and r_add.json()["default_model"] == "qwen3.5:14b"
    assert client.get("/ollama/models").json()["active"] == "qwen3.5:14b"
    assert client.post("/ollama/chat", params={"query": "test"}).json()["model"] == "qwen3.5:14b"

    # Warmup & persona routes
    assert client.post("/ollama/warmup").json()["ok"] is True
    assert client.get("/ollama/personas").json()["items"] == ["glados", "sentry"]
    assert client.post("/ollama/persona/select", params={"name": "glados"}).json()["active"] == "glados"
    assert client.post("/ollama/chat", params={"query": "kimsin"}).json()["persona"] == "glados"
    assert client.post("/ollama/persona/select", params={"name": "../evil"}).status_code == 400


def test_persona_create_from_url_security_and_translator_newline_and_tags(tmp_path: Path, monkeypatch) -> None:
    app = FastAPI()
    cfg = {"persona": {"default": "sentry", "dir": str(tmp_path)}, "ollama": {"model": "qwen3.5:9b"}}
    rt = {"active_persona": "sentry", "persona_text": "hi", "_persona_cache": {}}
    app.include_router(get_persona_router(cfg, None, "ollama", True, False, 60, rt), prefix="/ollama")
    client = TestClient(app)

    assert client.post("/ollama/persona/create_from_url", params={"name": "../escape", "url": "https://example.com"}).status_code == 400
    assert client.post("/ollama/persona/create_from_url", params={"name": "bot2", "url": "file:///etc/passwd"}).status_code == 400

    class _Resp:
        content = b"You are a kind helper."
        text = "You are a kind helper."

        def raise_for_status(self):
            return None

    seen_timeout = []

    def _fake_get(url, timeout=None):
        seen_timeout.append((url, timeout))
        return _Resp()

    monkeypatch.setattr("modules.ai_provider.api.persona_routes.requests.get", _fake_get)
    r_ok = client.post("/ollama/persona/create_from_url", params={"name": "helper_1", "url": "https://example.com/p.txt"})
    assert r_ok.status_code == 200
    assert seen_timeout[0][1] == 10.0
    assert (tmp_path / "helper_1" / "persona.txt").read_text(encoding="utf-8") == "You are a kind helper."

    # Translator uses real newline in prompt and stays thread-safe
    prompts = []

    class _TrClient:
        model = "qwen3.5:9b"

        def chat(self, messages, format=None, *, options=None, model=None):
            prompts.append(messages[-1]["content"])
            return {"message": {"content": "hello"}}

    tr = OllamaTranslator(_TrClient(), {"enabled": True, "default_source_lang": "tr"})
    out = tr.translate("merhaba", "tr", "en")
    assert out == "hello"
    assert "\\n" not in prompts[0] and "\n" in prompts[0]

    # Action tags parser
    cleaned, actions = extract_llm_tags("Selam [cmd:nod] [[servo pan=90 speed=1.5 ok=true]]")
    assert cleaned == "Selam"
    assert actions["commands"] == ["nod"]
    assert actions["blocks"] == [{"type": "servo", "attrs": {"pan": 90, "speed": 1.5, "ok": True}}]
