from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

try:
    import requests
except Exception:
    requests = None


class EspTransportMixin:
    """ESP-Link HTTP transport methods for Arduino service."""

    _logger: logging.Logger
    _esp_base_url: str
    _esp_request_path: str
    _esp_send_path: str
    _esp_health_path: str
    _esp_timeout: float
    _esp_connect_timeout: float
    _esp_fail_streak: int
    _esp_paused_until: float
    _esp_pause_after: int
    _esp_pause_sec: float
    _esp_pause_logged: bool
    _esp_http: Any
    _esp_lock: threading.RLock
    _metrics: Dict[str, int]
    cfg: Dict[str, Any]
    _resolve_request_timeout: Callable[[Optional[float]], float]
    _execute_with_retries: Callable[[Callable[[int], Any]], Any]
    _response_matches_request: Callable[[Dict[str, Any], Optional[int]], bool]
    _inc_metric: Callable[[str, int], None]

    def _get_esp_lock(self) -> threading.RLock:
        lock = getattr(self, "_esp_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._esp_lock = lock
        return lock

    def _esp_url(self, path: str) -> str:
        p = str(path or "").strip()
        if not p.startswith("/"):
            p = "/" + p
        return f"{self._esp_base_url}{p}"

    def _esp_is_paused(self) -> bool:
        with self._get_esp_lock():
            return time.monotonic() < self._esp_paused_until

    def _esp_note_failure(self, exc: Exception) -> None:
        with self._get_esp_lock():
            self._esp_fail_streak += 1
            if self._esp_fail_streak < self._esp_pause_after:
                return
            self._esp_paused_until = time.monotonic() + self._esp_pause_sec
            if not self._esp_pause_logged:
                self._logger.warning(
                    "ESP bridge unreachable after %d failures (%s); pausing HTTP for %.0fs",
                    self._esp_fail_streak,
                    exc.__class__.__name__,
                    self._esp_pause_sec,
                )
                self._esp_pause_logged = True

    def _esp_note_success(self) -> None:
        with self._get_esp_lock():
            self._esp_fail_streak = 0
            self._esp_paused_until = 0.0
            self._esp_pause_logged = False

    def _esp_post(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if requests is None and getattr(self, "_esp_http", None) is None:
            raise RuntimeError("requests is required for ESP HTTP transport")
        req_timeout = max(0.05, float(timeout if timeout is not None else self._esp_timeout))
        conn_timeout = max(0.05, float(self._esp_connect_timeout))
        url = self._esp_url(path)

        with self._get_esp_lock():
            now = time.monotonic()
            if now < self._esp_paused_until:
                retry_in = max(0, int(self._esp_paused_until - now))
                raise RuntimeError(f"ESP bridge paused (unreachable); retry in {retry_in}s")
            client = self._esp_http if self._esp_http is not None else requests
            try:
                resp = client.post(
                    url,
                    json=payload,
                    params=params,
                    timeout=(conn_timeout, req_timeout),
                )
            except Exception as exc:
                self._esp_note_failure(exc)
                raise

        if resp.status_code != 200:
            err = RuntimeError(f"ESP bridge HTTP {resp.status_code}: {resp.text[:200]}")
            self._esp_note_failure(err)
            raise err
        try:
            data = resp.json()
        except Exception as exc:
            wrapped = RuntimeError(f"ESP bridge returned non-JSON payload: {exc}")
            self._esp_note_failure(wrapped)
            raise wrapped from exc
        if not isinstance(data, dict):
            err = RuntimeError("ESP bridge response must be a JSON object")
            self._esp_note_failure(err)
            raise err
        self._esp_note_success()
        return data

    def _request_locked_esp(
        self, obj: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        eff_timeout = self._resolve_request_timeout(timeout)
        try:
            want_seq = int(obj["seq"]) if obj.get("seq") is not None else None
        except (TypeError, ValueError):
            want_seq = None

        def _once(_attempt: int) -> Dict[str, Any]:
            data = self._esp_post(
                self._esp_request_path,
                payload=obj,
                timeout=eff_timeout,
                params={"timeout": eff_timeout},
            )
            if hasattr(self, "_inc_metric"):
                self._inc_metric("tx_count", 1)
            else:
                self._metrics["tx_count"] += 1
            resp = data.get("resp") if isinstance(data, dict) and "resp" in data else data
            if not isinstance(resp, dict):
                raise RuntimeError("ESP bridge response missing 'resp' object")
            if not self._response_matches_request(resp, want_seq):
                raise RuntimeError(f"ESP bridge seq mismatch (wanted={want_seq}, got={resp})")
            if hasattr(self, "_ingest_message"):
                self._ingest_message(resp)
            return resp

        return self._execute_with_retries(_once)
