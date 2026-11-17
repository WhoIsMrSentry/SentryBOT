from __future__ import annotations

from contextlib import contextmanager
import heapq
import itertools
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Protocol, Tuple

import requests

from .google_ai_client import GoogleAIStudioClient
from modules.common.ollama_url import normalize_ollama_url

logger = logging.getLogger("ollama.clients")

_GOOGLE_API_KEY_PLACEHOLDERS = {
    "your-google-api-key",
    "your_google_api_key",
    "your-api-key",
    "changeme",
    "replace_me",
    "replace-with-your-key",
}


class CircuitOpenError(RuntimeError):
    """Raised when Ollama requests fail fast due to an open circuit breaker."""


class _CircuitBreaker:
    """Thread-safe consecutive-failure circuit breaker for remote Ollama bridges."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout_s: float = 15.0) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_timeout_s = max(0.5, float(recovery_timeout_s))
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until = 0.0

    def allow_request(self) -> bool:
        with self._lock:
            if self._open_until <= 0.0:
                return True
            if time.monotonic() >= self._open_until:
                return True  # half-open probe allowed
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open_until = time.monotonic() + self.recovery_timeout_s

    def state(self) -> Dict[str, Any]:
        with self._lock:
            remaining = max(0.0, self._open_until - time.monotonic()) if self._open_until > 0.0 else 0.0
            is_open = self._open_until > 0.0 and remaining > 0.0
            return {
                "state": "open" if is_open else "closed",
                "failures": self._failures,
                "threshold": self.failure_threshold,
                "cooldown_remaining_s": round(remaining, 2),
            }


def _sanitize_google_api_key(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in _GOOGLE_API_KEY_PLACEHOLDERS:
        return ""
    if "your-google-api-key" in lowered:
        return ""
    return value


class PriorityInferenceLock:
    """Öncelikli çıkarım kuyruğu: Kullanıcı sesli komutları (0) arka plan düşüncelerinin (2) önüne geçer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._counter = itertools.count()
        self._queue: List[Tuple[int, int, threading.Event]] = []

    @contextmanager
    def acquire(self, priority: int = 1):
        evt = threading.Event()
        with self._lock:
            if not self._active and not self._queue:
                self._active = True
                got_lock = True
            else:
                heapq.heappush(self._queue, (int(priority), next(self._counter), evt))
                got_lock = False

        if not got_lock:
            evt.wait()

        try:
            yield
        finally:
            with self._lock:
                if self._queue:
                    _, _, next_evt = heapq.heappop(self._queue)
                    self._active = True
                    next_evt.set()
                else:
                    self._active = False


_INFERENCE_SCHEDULER = PriorityInferenceLock()


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        request_timeout: float = 60.0,
        *,
        cb_failure_threshold: int = 3,
        cb_recovery_timeout_s: float = 15.0,
    ) -> None:
        self.base_url = normalize_ollama_url(base_url)
        self.model = model
        self.timeout = float(request_timeout)
        self._session = requests.Session()
        self._breaker = _CircuitBreaker(
            failure_threshold=cb_failure_threshold,
            recovery_timeout_s=cb_recovery_timeout_s,
        )

    def _http_post(self, url: str, **kwargs: Any) -> requests.Response:
        post_fn = getattr(requests, "post", None)
        if getattr(post_fn, "__module__", "") == "requests.api":
            return self._session.post(url, **kwargs)
        return requests.post(url, **kwargs)

    def _http_get(self, url: str, **kwargs: Any) -> requests.Response:
        get_fn = getattr(requests, "get", None)
        if getattr(get_fn, "__module__", "") == "requests.api":
            return self._session.get(url, **kwargs)
        return requests.get(url, **kwargs)

    def circuit_state(self) -> Dict[str, Any]:
        return self._breaker.state()

    def create_model(self, name: str, modelfile: str) -> bool:
        url = f"{self.base_url}/api/create"
        payload = {"name": name, "modelfile": modelfile, "stream": False}
        try:
            resp = self._http_post(url, json=payload, timeout=float(self.timeout * 2))
            resp.raise_for_status()
            logger.info("Ollama model '%s' created/updated successfully.", name)
            return True
        except Exception as exc:
            logger.error("Failed to create Ollama model '%s': %s", name, exc)
            return False

    def pull_model(self, name: str) -> bool:
        model_name = str(name or "").strip()
        if not model_name:
            return False

        url = f"{self.base_url}/api/pull"
        payload = {"name": model_name, "stream": False}
        try:
            resp = self._http_post(url, json=payload, timeout=float(self.timeout * 4))
            resp.raise_for_status()
            logger.info("Ollama model '%s' pulled successfully.", model_name)
            return True
        except Exception as exc:
            logger.error("Failed to pull Ollama model '%s': %s", model_name, exc)
            return False

    def is_alive(self, timeout: float = 2.0) -> bool:
        """Probe remote Ollama bridge health."""
        url = f"{self.base_url}/api/version"
        try:
            resp = self._http_get(url, timeout=float(timeout))
            return resp.status_code == 200
        except Exception:
            try:
                resp = self._http_get(f"{self.base_url}/api/tags", timeout=float(timeout))
                return resp.status_code == 200
            except Exception:
                return False

    def list_models(self) -> List[str]:
        url = f"{self.base_url}/api/tags"
        try:
            resp = self._http_get(url, timeout=float(self.timeout))
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        except Exception as exc:
            logger.error("Failed to list Ollama models: %s", exc)
            return []

        items = data.get("models", []) if isinstance(data, dict) else []
        names: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name:
                names.append(name)
        return names

    @staticmethod
    def _normalize_chat_response(data: Any) -> Dict[str, Any]:
        if isinstance(data, dict) and "message" in data:
            return data
        if isinstance(data, dict) and "choices" in data:
            try:
                content = data["choices"][0]["message"]["content"]
            except Exception:
                content = ""
            return {"message": {"content": content}, "raw": data}
        return {"message": {"content": str(data)}, "raw": data}

    def chat(
        self,
        messages: List[Dict[str, str]],
        format: Optional[Any] = None,
        *,
        options: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        priority: int = 1,
    ) -> Dict[str, Any]:
        if not self._breaker.allow_request():
            raise CircuitOpenError("Ollama circuit breaker is open")

        selected_model = model or self.model
        merged_options: Dict[str, Any] = {"temperature": 0.6, "num_ctx": 8192}
        if isinstance(options, dict):
            merged_options.update(options)

        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": getattr(self, "keep_alive", -1),
            "format": format,
            "options": merged_options,
        }

        with _INFERENCE_SCHEDULER.acquire(priority=priority):
            last_err: Optional[Exception] = None
            for attempt in range(2):
                try:
                    resp = self._http_post(url, json=payload, timeout=float(self.timeout))
                    resp.raise_for_status()
                    data = resp.json()
                    self._breaker.record_success()
                    return self._normalize_chat_response(data)
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                    last_err = exc
                    if attempt == 0:
                        time.sleep(0.2)
                        continue
                    self._breaker.record_failure()
                    raise
                except requests.HTTPError as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status is not None and int(status) >= 500:
                        self._breaker.record_failure()
                    raise
            if last_err:
                raise last_err
            raise RuntimeError("Ollama chat failed without response")

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        format: Optional[Any] = None,
        *,
        options: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        priority: int = 1,
    ) -> Iterator[Dict[str, Any]]:
        """Stream NDJSON response tokens from Ollama /api/chat under priority lock."""
        if not self._breaker.allow_request():
            raise CircuitOpenError("Ollama circuit breaker is open")

        selected_model = model or self.model
        merged_options: Dict[str, Any] = {"temperature": 0.6, "num_ctx": 8192}
        if isinstance(options, dict):
            merged_options.update(options)

        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "stream": True,
            "think": False,
            "keep_alive": getattr(self, "keep_alive", -1),
            "format": format,
            "options": merged_options,
        }

        with _INFERENCE_SCHEDULER.acquire(priority=priority):
            try:
                resp = self._http_post(url, json=payload, timeout=float(self.timeout), stream=True)
                resp.raise_for_status()
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        yield {"delta": line, "done": False, "raw": line}
                        continue
                    msg = chunk.get("message") if isinstance(chunk, dict) else None
                    delta = str(msg.get("content", "") if isinstance(msg, dict) else chunk.get("response", ""))
                    done = bool(chunk.get("done", False)) if isinstance(chunk, dict) else False
                    yield {"delta": delta, "done": done, "raw": chunk}
                self._breaker.record_success()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                self._breaker.record_failure()
                raise
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and int(status) >= 500:
                    self._breaker.record_failure()
                raise


class LLMClientProtocol(Protocol):
    model: str

    def chat(
        self,
        messages: List[Dict[str, str]],
        format: Optional[Any] = None,
        *,
        options: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    def create_model(self, name: str, modelfile: str) -> bool:
        ...

    def pull_model(self, name: str) -> bool:
        ...

    def list_models(self) -> List[str]:
        ...


def create_llm_client(cfg: Dict[str, Any]) -> Tuple[LLMClientProtocol, str]:
    from modules.common.config_loader import DEFAULT_GEMINI_MODEL

    llm_cfg = cfg.get("llm", {}) or {}
    provider = str(llm_cfg.get("provider", "ollama")).strip().lower() or "ollama"

    if provider in {"google", "google_ai_studio", "gemini"}:
        gcfg = cfg.get("google_ai_studio", {}) or {}
        api_key = _sanitize_google_api_key(gcfg.get("api_key", ""))
        if not api_key:
            api_key = _sanitize_google_api_key(os.environ.get("GOOGLE_API_KEY", ""))
        model = str(gcfg.get("model", DEFAULT_GEMINI_MODEL)).strip() or DEFAULT_GEMINI_MODEL
        base_url = str(gcfg.get("base_url", "https://generativelanguage.googleapis.com")).strip()
        timeout = float(gcfg.get("request_timeout", 60.0))
        if not api_key:
            raise RuntimeError("Google AI Studio selected but api_key is missing")
        return GoogleAIStudioClient(api_key=api_key, model=model, base_url=base_url, request_timeout=timeout), "google_ai_studio"

    ocfg = cfg.get("ollama", {}) or {}
    from modules.common.model_roles import resolve_role_model

    base_url = str(ocfg.get("base_url", "http:"))
    model = resolve_role_model(cfg, "chat", fallback=ocfg.get("model"))
    timeout = float(ocfg.get("request_timeout", 60.0))
    cb_thresh = int(ocfg.get("cb_failure_threshold", 3))
    cb_recovery = float(ocfg.get("cb_recovery_timeout_s", 15.0))
    return OllamaClient(
        base_url=base_url,
        model=model,
        request_timeout=timeout,
        cb_failure_threshold=cb_thresh,
        cb_recovery_timeout_s=cb_recovery,
    ), "ollama"
