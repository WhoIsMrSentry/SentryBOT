from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

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
    _metrics: Dict[str, int]
    cfg: Dict[str, Any]

    def _esp_url(self, path: str) -> str:
        p = str(path or "").strip()
        if not p.startswith("/"):
            p = "/" + p
        return f"{self._esp_base_url}{p}"

    def _esp_is_paused(self) -> bool:
        return time.time() < self._esp_paused_until

    def _esp_note_failure(self, exc: Exception) -> None:
        self._esp_fail_streak += 1
        if self._esp_fail_streak < self._esp_pause_after:
            return
        until = time.time() + self._esp_pause_sec
        self._esp_paused_until = until
        if not self._esp_pause_logged:
            self._logger.warning(
                "ESP bridge unreachable after %d failures (%s); pausing HTTP for %.0fs",
                self._esp_fail_streak,
                exc.__class__.__name__,
                self._esp_pause_sec,
            )
            self._esp_pause_logged = True

    def _esp_note_success(self) -> None:
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
        if requests is None:
            raise RuntimeError("requests is required for ESP HTTP transport")
        if self._esp_is_paused():
            raise RuntimeError(
                f"ESP bridge paused (unreachable); retry in {max(0, int(self._esp_paused_until - time.time()))}s"
            )
        req_timeout = float(timeout if timeout is not None else self._esp_timeout)
        req_timeout = max(0.05, req_timeout)
        conn_timeout = max(0.05, float(self._esp_connect_timeout))
        client = self._esp_http if self._esp_http is not None else requests
        try:
            resp = client.post(
                self._esp_url(path),
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
        self, obj: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        max_retries = int(self.cfg.get("request_max_retries", 0) or 0)
        if timeout is None or timeout == 1.0:
            cfg_ms = int(self.cfg.get("request_timeout_ms", 1000) or 1000)
            timeout = float(cfg_ms) / 1000.0
        last_exc: Optional[Exception] = None
        for attempt in range(0, max_retries + 1):
            try:
                data = self._esp_post(
                    self._esp_request_path,
                    payload=obj,
                    timeout=float(timeout),
                    params={"timeout": float(timeout)},
                )
                self._metrics["tx_count"] += 1
                resp = (
                    data.get("resp")
                    if isinstance(data, dict) and "resp" in data
                    else data
                )
                if isinstance(resp, dict):
                    if hasattr(self, "_ingest_message"):
                        self._ingest_message(resp)
                    return resp
                raise RuntimeError("ESP bridge response missing 'resp' object")
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(0.05)
                    continue
        if last_exc:
            raise last_exc
        raise TimeoutError("No response from ESP bridge")
