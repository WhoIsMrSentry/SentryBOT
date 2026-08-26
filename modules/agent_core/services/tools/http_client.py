from __future__ import annotations

import logging
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger("agent.tools.http")


class HttpClient:
    """Shared HTTP client for gateway communication."""

    def __init__(self, gateway_base_url: str, default_timeout: float = 2.0):
        self._gateway_base_url = gateway_base_url.rstrip("/")
        self._default_timeout = default_timeout

    def _url(self, path: str) -> str:
        return f"{self._gateway_base_url}/{str(path).lstrip('/')}"

    def get(self, path: str, timeout: Optional[float] = None) -> requests.Response:
        return requests.get(self._url(path), timeout=timeout or self._default_timeout)

    def post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        return requests.post(
            self._url(path), json=json_data or {}, timeout=timeout or self._default_timeout
        )

    def _handle_response(
        self, resp: requests.Response, error_prefix: str = "Request"
    ) -> str:
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {}
        return f"{error_prefix} failed: HTTP {resp.status_code}"
