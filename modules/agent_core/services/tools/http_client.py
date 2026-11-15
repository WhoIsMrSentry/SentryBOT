from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("agent.tools.http")


class HttpClient:
    """Shared HTTP client with persistent connection pooling for gateway communication."""

    def __init__(self, gateway_base_url: str, default_timeout: float = 2.0):
        self._gateway_base_url = gateway_base_url.rstrip("/")
        self._default_timeout = default_timeout
        self._session = requests.Session()

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def _url(self, path: str) -> str:
        return f"{self._gateway_base_url}/{str(path).lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = self._url(path)
        fn = getattr(requests, method.lower(), None)
        if fn is not None and getattr(fn, "__module__", "") != "requests.api":
            return fn(url, **kwargs)
        req_fn = getattr(requests, "request", None)
        if req_fn is not None and getattr(req_fn, "__module__", "") != "requests.api":
            return req_fn(method.upper(), url, **kwargs)
        return self._session.request(method.upper(), url, **kwargs)

    def get(self, path: str, timeout: Optional[float] = None) -> requests.Response:
        return self._request("GET", path, timeout=timeout or self._default_timeout)

    def post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        return self._request(
            "POST",
            path,
            json=json_data or {},
            params=params,
            timeout=timeout or self._default_timeout,
        )

    def arduino_request(
        self,
        payload: Dict[str, Any],
        timeout: float = 1.0,
    ) -> Any:
        """Send a synchronous Arduino command request via the Gateway /arduino/request endpoint."""
        resp = self.post("arduino/request", json_data=payload, params={"timeout": float(timeout)}, timeout=timeout + 1.0)
        if getattr(resp, "status_code", 500) != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if isinstance(data, dict) and "resp" in data:
            return data.get("resp")
        return data
