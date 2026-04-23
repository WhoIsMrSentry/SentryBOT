from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from .config_loader import load_config


class xEspLinkService:
    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        self.cfg = load_config(overrides=config_overrides)
        self.base_url = str(self.cfg.get("base_url", "http://sentrybot.local")).rstrip("/")
        paths = self.cfg.get("paths", {}) or {}
        self.path_health = str(paths.get("health", "/healthz"))
        self.path_send = str(paths.get("send", "/send"))
        self.path_request = str(paths.get("request", "/request"))
        tmo = self.cfg.get("timeouts", {}) or {}
        self.connect_timeout = float(tmo.get("connect_s", 0.4) or 0.4)
        self.io_timeout = float(tmo.get("io_s", 1.2) or 1.2)

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _post(self, path: str, payload: Dict[str, Any], params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        resp = requests.post(
            self._url(path),
            json=payload,
            params=params,
            timeout=(self.connect_timeout, float(timeout if timeout is not None else self.io_timeout)),
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ESP bridge HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError("ESP bridge returned non-object JSON")
        return data

    def healthz(self) -> Dict[str, Any]:
        resp = requests.get(self._url(self.path_health), timeout=(self.connect_timeout, self.io_timeout))
        if resp.status_code != 200:
            return {"ok": False, "status_code": resp.status_code}
        try:
            data = resp.json()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"ok": True}

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post(self.path_send, payload)

    def request(self, payload: Dict[str, Any], timeout: float = 1.0) -> Dict[str, Any]:
        return self._post(self.path_request, payload, params={"timeout": float(timeout)}, timeout=float(timeout))
