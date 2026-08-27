from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
import time
from typing import Any, Callable, Dict, Optional

import requests

from .client_parts import ClientHardwareMixin, ClientSpeechMixin, ClientVisionMixin

logger = logging.getLogger("autonomy.client")


class ServiceClient(ClientHardwareMixin, ClientVisionMixin, ClientSpeechMixin):
    def __init__(self, base_urls=None, config=None):
        try:
            from modules.gateway.url import gateway_url, resolve_gateway_base_url, rewrite_loopback_urls

            base = resolve_gateway_base_url()
            self.urls = rewrite_loopback_urls(dict(base_urls or {}), base)
            self.urls.setdefault("agent_core", gateway_url(base, "/agent"))
            self.urls.setdefault("gateway", base)
        except Exception:
            self.urls = dict(base_urls or {})
            self.urls.setdefault("gateway", "http://127.0.0.1:8080")
        cfg = config or {}
        self.speech_quiet_cfg = dict(cfg.get("speech_quiet_hours", {}))
        self.offline_cfg = dict(cfg.get("offline_mode", {}))
        self.request_timeouts = dict(cfg.get("request_timeouts", {}))
        speech_cfg = cfg.get("speech", {}) if isinstance(cfg.get("speech"), dict) else {}
        self.speech_stream_cfg = dict(speech_cfg)
        self._availability_cache: Dict[str, tuple[float, bool]] = {}
        self.head_arbiter = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="autonomy_client_worker")

    def submit_background(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        return self._executor.submit(fn, *args, **kwargs)

    def close(self) -> None:
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass

    def attach_head_arbiter(self, arbiter: Any) -> None:
        self.head_arbiter = arbiter

    def _agent_core_url(self) -> str:
        try:
            from modules.gateway.url import gateway_url, resolve_gateway_base_url
            return str(self.urls.get("agent_core") or gateway_url(resolve_gateway_base_url(), "/agent"))
        except Exception:
            return str(self.urls.get("agent_core") or "http://127.0.0.1:8080/agent")

    def _post(self, service: str, endpoint: str, json: Any = None, params: Any = None, timeout_s: Optional[float] = None) -> Any:
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            timeout = float(timeout_s) if timeout_s is not None else float(self.request_timeouts.get("default_post_s", 1.0))
            resp = requests.post(full_url, json=json, params=params, timeout=timeout)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug("Failed to post to %s: %s", service, e)
            return None

    def _get(self, service: str, endpoint: str, params: Any = None, timeout_s: Optional[float] = None) -> Any:
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            timeout = float(timeout_s) if timeout_s is not None else float(self.request_timeouts.get("default_get_s", 1.0))
            resp = requests.get(full_url, params=params, timeout=timeout)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug("Failed to get from %s: %s", service, e)
            return None

    def _arduino_request(self, payload: Any, timeout: float = 1.0) -> Any:
        now = time.time()
        cooldown_until = float(getattr(self, "_arduino_fail_cooldown_until", 0.0) or 0.0)
        if now < cooldown_until:
            return None
        data = self._post("arduino", "/request", json=payload, params={"timeout": float(timeout)})
        if not data:
            self._arduino_fail_cooldown_until = now + 4.0
            return None
        self._arduino_fail_cooldown_until = 0.0
        if isinstance(data, dict) and "resp" in data:
            return data.get("resp")
        return data

    def push_interaction_event(self, event_type: str, data: Any = None) -> Any:
        return self._post("interactions", "/event", {"type": event_type, "data": data})

    def set_expression_event(self, event_type: str, data: Any = None) -> Any:
        return self._post("expression", "/event", {"type": str(event_type), "data": data or {}})

    def get_operational_mode(self) -> str:
        data = self._get("state_manager", "/get")
        if isinstance(data, dict):
            return str(data.get("operational", "idle")).strip().lower() or "idle"
        return "idle"

    def is_service_available(self, service: str) -> bool:
        svc = str(service or "").strip().lower()
        if not svc:
            return False
        ttl = float(self.offline_cfg.get("availability_ttl_s", 5.0))
        now = time.time()
        cached = self._availability_cache.get(svc)
        if isinstance(cached, tuple) and len(cached) == 2:
            ts, ok = cached
            if now - float(ts) <= ttl:
                return bool(ok)

        url = self.urls.get(svc)
        if not url:
            self._availability_cache[svc] = (now, False)
            return False

        endpoint = "/status" if svc in ("speak", "speech") else "/healthz"
        try:
            resp = requests.get(f"{url}{endpoint}", timeout=0.6)
            ok = resp.status_code == 200
            if ok and svc == "ollama":
                try:
                    payload = resp.json()
                    ok = bool(payload.get("ok", False))
                except Exception:
                    ok = False
            elif ok and svc == "speak":
                try:
                    payload = resp.json()
                    ok = bool(payload.get("ready", False))
                except Exception:
                    ok = False
        except Exception:
            ok = False
        self._availability_cache[svc] = (now, ok)
        return ok

    def check_rfid(self, endpoint: str) -> bool:
        if not endpoint:
            return False
        try:
            from modules.gateway.url import resolve_config_url, resolve_gateway_base_url
            url = resolve_config_url(str(endpoint), self.urls.get("gateway") or resolve_gateway_base_url())
        except Exception:
            url = str(endpoint)
            if url.startswith("@gateway"):
                url = f"http://127.0.0.1:8080{url[len('@gateway'):]}"
        try:
            resp = requests.get(url, timeout=1.0)
            if resp.status_code != 200:
                return False
            data = resp.json()
            if isinstance(data, dict):
                return bool(data.get("authorized") or data.get("ok"))
            return bool(data)
        except Exception as exc:
            logger.debug("RFID check failed: %s", exc)
            return False

    def queue_action(self, action_type: str, priority: int = 50, ttl_ms: int = 5000, payload: Optional[dict] = None) -> Any:
        if payload is None:
            payload = {}
        url = self._agent_core_url()
        try:
            resp = requests.post(f"{url}/actions/queue", json={
                "type": action_type,
                "priority": priority,
                "ttl_ms": ttl_ms,
                "payload": payload,
            }, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug("Failed to queue action %s: %s", action_type, e)
            return None

    def world_memory_context(self, query: str, limit: int = 8) -> Any:
        return self._get("autonomy", "/memory/context", params={"q": str(query or ""), "limit": int(limit or 8)}, timeout_s=1.0)

    def world_memory_recall(self, query: str, limit: int = 8) -> Any:
        return self._get("autonomy", "/memory/search", params={"q": str(query or ""), "limit": int(limit or 8)}, timeout_s=1.0)

    def world_memory_observe(self, payload: dict | None = None) -> Any:
        return self._post("autonomy", "/memory/observe", json=payload or {}, timeout_s=1.0)

    def execute_rest_corner(self, payload: dict | None = None) -> Any:
        return self._post("autonomy", "/navigation/rest-corner", json=payload or {}, timeout_s=1.5)

    def emit_agent_event(self, event_type: str, payload: dict | None = None) -> Any:
        if payload is None:
            payload = {}
        url = self._agent_core_url()
        try:
            resp = requests.post(
                f"{url}/events",
                json={"type": str(event_type), "payload": payload},
                timeout=1.0,
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug("Failed to emit agent event %s: %s", event_type, e)
            return None

    async def _async_post(self, service: str, endpoint: str, json: dict | None = None,
                          params: dict | None = None, timeout: float = 2.0) -> dict | None:
        url = self.urls.get(service)
        if not url:
            return None
        try:
            from modules.common.http_client import get_http_client
            client = get_http_client(url, timeout)
            kwargs: Dict[str, Any] = {}
            if json is not None:
                kwargs["json"] = json
            if params is not None:
                kwargs["params"] = params
            resp = await client.post(endpoint, **kwargs)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return {}
            return None
        except Exception as e:
            logger.debug("Async post to %s%s failed: %s", service, endpoint, e)
            return None

    async def _async_get(self, service: str, endpoint: str,
                         params: dict | None = None, timeout: float = 2.0) -> dict | None:
        url = self.urls.get(service)
        if not url:
            return None
        try:
            from modules.common.http_client import get_http_client
            client = get_http_client(url, timeout)
            kwargs: Dict[str, Any] = {}
            if params is not None:
                kwargs["params"] = params
            resp = await client.get(endpoint, **kwargs)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return {}
            return None
        except Exception as e:
            logger.debug("Async get from %s%s failed: %s", service, endpoint, e)
            return None

    async def async_wake(self) -> dict:
        return await self._async_post("autonomy", "/start", timeout=2.0)

    async def async_sleep(self) -> dict:
        return await self._async_post("autonomy", "/stop", timeout=2.0)

    async def async_set_operational_mode(self, mode: str) -> dict:
        return await self._async_post(
            "state_manager", "/set/operational",
            json={"mode": str(mode)},
            timeout=1.0,
        )

    async def async_queue_action(
        self,
        action_type: str,
        priority: int = 50,
        ttl_ms: int = 5000,
        payload: dict | None = None,
    ) -> dict:
        return await self._async_post(
            "agent_core", "/actions/queue",
            json={
                "type": action_type,
                "priority": priority,
                "ttl_ms": ttl_ms,
                "payload": payload or {},
            },
            timeout=2.0,
        )

    async def async_push_interaction_event(self, event_type: str, data: dict | None = None) -> dict:
        return await self._async_post(
            "interactions", "/event",
            json={"type": event_type, "data": data or {}},
            timeout=1.0,
        )

    async def async_search_memory(self, query: str, limit: int = 5) -> dict:
        if not query:
            return {"ok": False, "error": "query is empty"}
        try:
            url = self._agent_core_url()
            from modules.common.http_client import get_http_client
            base = url.replace("/agent", "")
            client = get_http_client(base, timeout=2.0)
            resp = await client.get(
                "/agent/memory/search",
                params={"query": query, "limit": limit},
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug("async_search_memory fallback failed: %s", e)
        return await self._async_get("agent_core", "/memory/search", params={"query": query, "limit": limit})

    async def async_close(self) -> None:
        return None
