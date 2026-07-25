"""Async HTTP client for SentryBOT modules.

Provides a singleton-per-base-url AsyncHTTPClient using httpx with:
- Connection pooling
- Configurable timeouts and retries
- Circuit breaker pattern
- Request/response logging with latency metrics
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("common.http")

# Thread-safe singleton registry
_client_lock = threading.Lock()
_clients: dict[str, "AsyncHTTPClient"] = {}


@dataclass
class RetryPolicy:
    """Retry configuration for failed requests."""
    max_attempts: int = 3
    base_delay: float = 0.2
    max_delay: float = 2.0
    exponential_base: float = 2.0
    retry_on_status: set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})
    retry_on_exceptions: tuple[type[Exception], ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
    )


@dataclass
class CircuitBreakerState:
    """Circuit breaker state for a host."""
    failures: int = 0
    last_failure: float = 0
    state: str = "closed"  # closed, open, half-open
    success_count: int = 0


class CircuitBreaker:
    """Simple circuit breaker for failing hosts."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._states: dict[str, CircuitBreakerState] = {}
        self._lock = threading.Lock()
    
    def _get_state(self, host: str) -> CircuitBreakerState:
        with self._lock:
            if host not in self._states:
                self._states[host] = CircuitBreakerState()
            return self._states[host]
    
    def can_execute(self, host: str) -> bool:
        state = self._get_state(host)
        now = time.time()
        
        if state.state == "closed":
            return True
        
        if state.state == "open":
            if now - state.last_failure >= self.recovery_timeout:
                with self._lock:
                    state.state = "half-open"
                    state.success_count = 0
                    logger.info("Circuit breaker for %s: half-open", host)
                    return True
            return False
        
        # half-open
        return state.success_count < self.half_open_max_calls
    
    def record_success(self, host: str) -> None:
        state = self._get_state(host)
        if state.state == "half-open":
            state.success_count += 1
            if state.success_count >= self.half_open_max_calls:
                state.state = "closed"
                state.failures = 0
                logger.info("Circuit breaker for %s: closed", host)
        elif state.state == "closed":
            state.failures = max(0, state.failures - 1)
    
    def record_failure(self, host: str) -> None:
        state = self._get_state(host)
        state.failures += 1
        state.last_failure = time.time()
        
        if state.state == "half-open":
            state.state = "open"
            logger.warning("Circuit breaker for %s: open (half-open failure)", host)
        elif state.state == "closed" and state.failures >= self.failure_threshold:
            state.state = "open"
            logger.warning("Circuit breaker for %s: open", host)


class AsyncHTTPClient:
    """Async HTTP client with pooling, retries, and circuit breaker."""
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        connect_timeout: float = 5.0,
        max_connections: int = 20,
        max_keepalive: int = 5,
        keepalive_expiry: float = 30.0,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        default_headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout, connect=connect_timeout)
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
            keepalive_expiry=keepalive_expiry,
        )
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=limits,
            headers=default_headers or {},
            follow_redirects=True,
        )
        
        # Metrics
        self._request_count = 0
        self._error_count = 0
        self._total_latency = 0.0
    
    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "requests": self._request_count,
            "errors": self._error_count,
            "avg_latency_ms": round(self._total_latency / self._request_count * 1000, 2) if self._request_count else 0,
            "circuit_breakers": {
                host: state.state for host, state in self.circuit_breaker._states.items()
            },
        }
    
    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return path
    
    def _extract_host(self, url: str) -> str:
        """Extract host:port from URL for circuit breaker."""
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        host = url.split("/")[0]
        return host
    
    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        url = self._build_url(path)
        host = self._extract_host(url)
        
        # Check circuit breaker
        if not self.circuit_breaker.can_execute(host):
            raise httpx.ConnectError(f"Circuit breaker open for {host}")
        
        attempt = 0
        last_exception = None
        
        while attempt <= self.retry_policy.max_attempts:
            attempt += 1
            start_time = time.perf_counter()
            
            try:
                self._request_count += 1
                
                if method == "GET":
                    resp = await self._client.get(url, **kwargs)
                elif method == "POST":
                    resp = await self._client.post(url, **kwargs)
                elif method == "PUT":
                    resp = await self._client.put(url, **kwargs)
                elif method == "PATCH":
                    resp = await self._client.patch(url, **kwargs)
                elif method == "DELETE":
                    resp = await self._client.delete(url, **kwargs)
                else:
                    resp = await self._client.request(method, url, **kwargs)
                
                latency = time.perf_counter() - start_time
                self._total_latency += latency
                
                # Check if we should retry on status
                if resp.status_code in self.retry_policy.retry_on_status:
                    raise httpx.HTTPStatusError(
                        f"Retryable status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                
                resp.raise_for_status()
                self.circuit_breaker.record_success(host)
                return resp
                
            except self.retry_policy.retry_on_exceptions as e:
                last_exception = e
                self.circuit_breaker.record_failure(host)
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                self.circuit_breaker.record_failure(host)
                
                # Don't retry 4xx errors (except 429)
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise
                
            except Exception as e:
                last_exception = e
                self.circuit_breaker.record_failure(host)
            
            # Retry delay
            if attempt <= self.retry_policy.max_attempts:
                delay = min(
                    self.retry_policy.base_delay * (self.retry_policy.exponential_base ** (attempt - 1)),
                    self.retry_policy.max_delay,
                )
                await asyncio.sleep(delay)
        
        self._error_count += 1
        raise last_exception or RuntimeError("Request failed after retries")
    
    # Convenience methods
    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("GET", path, **kwargs)
    
    async def post(self, path: str, json: Any = None, **kwargs) -> httpx.Response:
        if json is not None:
            kwargs.setdefault("json", json)
        return await self._request_with_retry("POST", path, **kwargs)
    
    async def put(self, path: str, json: Any = None, **kwargs) -> httpx.Response:
        if json is not None:
            kwargs.setdefault("json", json)
        return await self._request_with_retry("PUT", path, **kwargs)
    
    async def patch(self, path: str, json: Any = None, **kwargs) -> httpx.Response:
        if json is not None:
            kwargs.setdefault("json", json)
        return await self._request_with_retry("PATCH", path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("DELETE", path, **kwargs)
    
    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry(method, path, **kwargs)
    
    @asynccontextmanager
    async def stream(self, method: str, path: str, **kwargs):
        """Stream response for large payloads."""
        url = self._build_url(path)
        host = self._extract_host(url)
        
        if not self.circuit_breaker.can_execute(host):
            raise httpx.ConnectError(f"Circuit breaker open for {host}")
        
        async with self._client.stream(method, url, **kwargs) as resp:
            try:
                resp.raise_for_status()
                yield resp
            finally:
                await resp.aclose()
    
    async def close(self) -> None:
        await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()


def get_http_client(
    base_url: str,
    timeout: float = 10.0,
    **kwargs
) -> AsyncHTTPClient:
    """Get or create a singleton AsyncHTTPClient for the given base_url."""
    key = f"{base_url}:{timeout}"
    
    with _client_lock:
        if key not in _clients:
            _clients[key] = AsyncHTTPClient(base_url, timeout, **kwargs)
        return _clients[key]


async def close_all_clients() -> None:
    """Close all registered clients. Call on shutdown."""
    with _client_lock:
        for client in _clients.values():
            await client.close()
        _clients.clear()


# For backward compatibility and sync-only contexts
class SyncHTTPClient:
    """Synchronous wrapper for quick one-off requests (use async client in services)."""
    
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
    
    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = path if path.startswith("http") else ("/" + path.lstrip("/"))
        resp = self._client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp
    
    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._request("GET", path, **kwargs)
    
    def post(self, path: str, json: Any = None, **kwargs) -> httpx.Response:
        if json is not None:
            kwargs.setdefault("json", json)
        return self._request("POST", path, **kwargs)
    
    def put(self, path: str, json: Any = None, **kwargs) -> httpx.Response:
        if json is not None:
            kwargs.setdefault("json", json)
        return self._request("PUT", path, **kwargs)
    
    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self._request("DELETE", path, **kwargs)
    
    def close(self):
        self._client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


__all__ = [
    "AsyncHTTPClient",
    "SyncHTTPClient",
    "RetryPolicy",
    "CircuitBreaker",
    "get_http_client",
    "close_all_clients",
]