"""Standard Health Response for SentryBOT.

Provides standardized health check responses across all modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, List
from enum import Enum


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthDetail:
    """Individual health check detail."""
    name: str
    status: str  # healthy, degraded, unhealthy
    message: str = ""
    latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthResponse:
    """Standardized health check response.
    
    Follows the format:
    {
        "status": "healthy|degraded|unhealthy",
        "timestamp": "2024-01-15T10:30:00Z",
        "version": "1.0.0",
        "uptime_seconds": 3600,
        "checks": {
            "database": {"status": "healthy", "latency_ms": 5.2},
            "redis": {"status": "healthy", "latency_ms": 2.1}
        },
        "metadata": {
            "service": "my-service",
            "instance_id": "abc123"
        }
    }
    """
    status: str  # healthy, degraded, unhealthy
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    version: str = "1.0.0"
    uptime_seconds: Optional[float] = None
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "checks": self.checks,
            "metadata": self.metadata,
        }
    
    @classmethod
    def healthy(cls, **kwargs) -> "HealthResponse":
        """Create a healthy response."""
        return cls(status="healthy", **kwargs)
    
    @classmethod
    def degraded(cls, **kwargs) -> "HealthResponse":
        """Create a degraded response."""
        return cls(status="degraded", **kwargs)
    
    @classmethod
    def unhealthy(cls, **kwargs) -> "HealthResponse":
        """Create an unhealthy response."""
        return cls(status="unhealthy", **kwargs)


class HealthChecker:
    """Helper class for building health checks."""
    
    def __init__(self, service_name: str, version: str = "1.0.0"):
        self.service_name = service_name
        self.version = version
        self._checks: Dict[str, Callable[[], Dict[str, Any]]] = {}
        self.start_time = time.time()
    
    def add_check(self, name: str, check_fn: Callable[[], Dict[str, Any]]) -> "HealthChecker":
        """Add a health check function.
        
        The check function should return a dict with:
        - status: "healthy", "degraded", "unhealthy"
        - latency_ms: optional
        - message: optional
        - metadata: optional dict
        """
        self._checks[name] = check_fn
        return self
    
    def add_simple_check(self, name: str, check_fn: Callable[[], bool]) -> "HealthChecker":
        """Add a simple boolean check."""
        def wrapper():
            try:
                result = check_fn()
                return {"status": "healthy" if result else "unhealthy"}
            except Exception as e:
                return {"status": "unhealthy", "message": str(e)}
        self._checks[name] = wrapper
        return self
    
    def add_latency_check(self, name: str, check_fn: Callable[[], float], 
                          healthy_threshold_ms: float = 100,
                          degraded_threshold_ms: float = 500) -> "HealthChecker":
        """Add a latency-based check."""
        def wrapper():
            try:
                start = time.perf_counter()
                result = check_fn()
                latency_ms = (time.perf_counter() - start) * 1000
                
                if latency_ms <= healthy_threshold_ms:
                    status = "healthy"
                elif latency_ms <= degraded_threshold_ms:
                    status = "degraded"
                else:
                    status = "unhealthy"
                
                return {
                    "status": status,
                    "latency_ms": latency_ms,
                    "message": f"Latency: {latency_ms:.1f}ms"
                }
            except Exception as e:
                return {"status": "unhealthy", "message": str(e)}
        
        self._checks[name] = wrapper
        return self
    
    def run(self) -> Dict[str, Any]:
        """Run all checks and return aggregated response."""
        start = time.perf_counter()
        checks = {}
        overall_status = "healthy"
        
        for name, check_fn in self._checks.items():
            try:
                result = check_fn()
                if isinstance(result, dict):
                    check_result = result
                else:
                    check_result = {"status": "healthy" if result else "unhealthy"}
                
                if check_result.get("status") == "unhealthy":
                    overall_status = "unhealthy"
                elif check_result.get("status") == "degraded" and overall_status == "healthy":
                    overall_status = "degraded"
                
                check_result["name"] = name
                self._checks[name] = check_result
            
            except Exception as e:
                overall_status = "unhealthy"
                check_result = {
                    "name": name,
                    "status": "unhealthy",
                    "message": str(e),
                }
        
        latency_ms = (time.perf_counter() - time.perf_counter()) * 1000  # This will be 0, but placeholder
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.0.0",
            "checks": {k: v for k, v in self._checks.items() if isinstance(v, dict)},
            "metadata": {
                "service": self.service_name,
            },
        }
    
    def get_health_response(self) -> "HealthResponse":
        """Get a HealthResponse object."""
        result = self.run()
        return HealthResponse(
            status=result["status"],
            timestamp=result["timestamp"],
            version=self.version,
            checks=result.get("checks", {}),
            metadata=result.get("metadata", {}),
        )


def create_health_response(
    status: str,
    service: str,
    version: str = "1.0.0",
    uptime: Optional[float] = None,
    checks: Optional[Dict[str, Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a standard health response dict."""
    return {
        "status": status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": version,
        "uptime_seconds": uptime,
        "checks": checks or {},
        "metadata": {
            "service": service,
            **(metadata or {}),
        },
    }


def health_check_decorator(
    name: str,
    healthy_threshold_ms: float = 100,
    degraded_threshold_ms: float = 500,
) -> Callable:
    """Decorator for creating latency-based health checks.
    
    Usage:
        @health_check_decorator("database")
        def check_db():
            return db.ping()
    """
    def decorator(func: Callable) -> Callable:
        def wrapper() -> Dict[str, Any]:
            start = time.perf_counter()
            try:
                result = func()
                latency_ms = (time.perf_counter() - start) * 1000
                
                if latency_ms <= healthy_threshold_ms:
                    status = "healthy"
                elif latency_ms <= degraded_threshold_ms:
                    status = "degraded"
                else:
                    status = "unhealthy"
                
                return {
                    "status": status,
                    "latency_ms": latency_ms,
                    "message": f"Latency: {latency_ms:.1f}ms",
                }
            except Exception as e:
                return {
                    "status": "unhealthy",
                    "message": str(e),
                }
        
        wrapper.__name__ = f"health_check_{name}"
        return wrapper
    
    return decorator


# Standard check functions
def check_database(db, query: str = "SELECT 1") -> Dict[str, Any]:
    """Standard database health check."""
    return check_latency(lambda: db.execute(query), "database")


def check_redis(redis_client) -> Dict[str, Any]:
    """Standard Redis health check."""
    return check_latency(lambda: redis_client.ping(), "redis")


def check_http_endpoint(url: str, timeout: float = 5.0, expected_status: int = 200) -> Dict[str, Any]:
    """Check an HTTP endpoint."""
    import requests
    start = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout)
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code == expected_status:
            return {"status": "healthy", "latency_ms": latency_ms}
        else:
            return {
                "status": "unhealthy",
                "latency_ms": latency_ms,
                "message": f"Status {resp.status_code} != {expected_status}",
            }
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def check_disk_space(path: str = "/", min_free_gb: float = 1.0) -> Dict[str, Any]:
    """Check disk space."""
    import shutil
    try:
        total, used, free = shutil.disk_usage(path)
        free_gb = free / (1024**3)
        if free_gb >= min_free_gb:
            return {"status": "healthy", "free_gb": free_gb}
        else:
            return {"status": "unhealthy", "free_gb": free_gb, "message": f"Only {free_gb:.1f}GB free"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def check_memory(min_free_mb: float = 100.0) -> Dict[str, Any]:
    """Check available memory."""
    import psutil
    try:
        mem = psutil.virtual_memory()
        free_mb = mem.available / (1024**2)
        if free_mb >= min_free_mb:
            return {"status": "healthy", "free_mb": free_mb}
        else:
            return {"status": "unhealthy", "free_mb": free_mb}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def check_cpu(threshold_percent: float = 90.0) -> Dict[str, Any]:
    """Check CPU usage."""
    import psutil
    try:
        percent = psutil.cpu_percent(interval=0.1)
        if percent < threshold_percent:
            return {"status": "healthy", "cpu_percent": percent}
        else:
            return {"status": "unhealthy", "cpu_percent": percent}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


__all__ = [
    "HealthStatus",
    "HealthDetail",
    "HealthResponse",
    "HealthChecker",
    "create_health_response",
    "health_check_decorator",
    "check_database",
    "check_redis",
    "check_http_endpoint",
    "check_disk_space",
    "check_memory",
    "check_cpu",
]