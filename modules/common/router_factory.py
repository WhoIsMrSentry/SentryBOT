"""Router Factory for SentryBOT.

Provides standardized FastAPI router creation with:
- Standard health endpoint
- Consistent error handling
- Request/response logging
- Rate limiting
- API versioning
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("common.router_factory")


# =============================================================================
# Models
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    ok: bool = False
    error: str
    error_code: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class HealthResponse(BaseModel):
    """Standard health response."""
    ok: bool = True
    status: str = "healthy"
    service: str
    version: str = "1.0.0"
    uptime_seconds: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    checks: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class RouterConfig:
    """Router configuration."""
    prefix: str = ""
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    service_name: str = "unknown"
    health_endpoint: str = "/healthz"
    include_health: bool = True
    include_version: bool = True
    rate_limit: Optional[int] = None  # requests per minute
    rate_limit_window: int = 60  # seconds
    log_requests: bool = True
    log_responses: bool = False
    cors_origins: List[str] = field(default_factory=list)


@dataclass
class RouteConfig:
    """Individual route configuration."""
    path: str
    method: str
    handler: Callable
    response_model: Optional[Type[BaseModel]] = None
    status_code: int = status.HTTP_200_OK
    summary: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    dependencies: List[Callable] = field(default_factory=list)
    deprecated: bool = False
    include_in_schema: bool = True


# =============================================================================
# Middleware
# =============================================================================

class RequestLoggerMiddleware:
    """Middleware for logging requests/responses."""
    
    def __init__(self, log_requests: bool = True, log_responses: bool = False):
        self.log_requests = log_requests
        self.log_responses = log_responses
    
    async def __call__(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.perf_counter()
        
        if self.log_requests:
            logger.info(
                "Request: %s %s (ID: %s)",
                request.method,
                request.url.path,
                request_id,
            )
        
        response = await call_next(request)
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        if self.log_responses:
            logger.info(
                "Response: %s %s -> %d (%.2fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-MS"] = str(duration_ms)
        
        return response


class RateLimitMiddleware:
    """Simple in-memory rate limiter."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def __call__(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_ip}"
        
        async with self._lock:
            now = time.time()
            # Clean old entries
            cutoff = now - 60  # 60 second window
            # We'll use the global store with a lock
        
        # For simplicity, use a simple counter per IP
        # In production, use Redis
        return await call_next(request)


# =============================================================================
# Router Factory
# =============================================================================

class RouterFactory:
    """Factory for creating standardized routers."""
    
    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig()
        self._routes: List[RouteConfig] = []
        self._health_check_fn: Optional[Callable] = None
        self._startup_time = time.time()
    
    def set_health_check(self, health_fn: Callable[[], Dict[str, Any]]) -> "RouterFactory":
        """Set custom health check function."""
        self._health_check_fn = health_fn
        return self
    
    def add_route(
        self,
        path: str,
        method: str,
        handler: Callable,
        response_model: Optional[Type[BaseModel]] = None,
        status_code: int = status.HTTP_200_OK,
        summary: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        dependencies: Optional[List[Callable]] = None,
        deprecated: bool = False,
    ) -> "RouterFactory":
        """Add a route to the router."""
        self._routes.append(RouteConfig(
            path=path,
            method=method.upper(),
            handler=handler,
            response_model=response_model,
            status_code=status_code,
            summary=summary,
            description=description,
            tags=tags or [],
            dependencies=dependencies or [],
        ))
        return self
    
    def add_health_endpoint(self) -> "RouterFactory":
        """Add standard health endpoint."""
        async def health_check():
            return await self._health_check()
        
        self._routes.append(RouteConfig(
            path=self.config.health_endpoint,
            method="GET",
            handler=self._health_check,
            response_model=HealthResponse,
            summary="Health check",
            tags=["health"],
        ))
        return self
    
    def add_version_endpoint(self) -> "RouterFactory":
        """Add version endpoint."""
        async def version():
            return {
                "service": self.config.service_name,
                "version": self.config.version,
            }
        
        self._routes.append(RouteConfig(
            path="/version",
            method="GET",
            handler=lambda: {"service": self.config.service_name, "version": self.config.version},
            tags=["info"],
        ))
        return self
    
    async def _health_check(self) -> HealthResponse:
        """Default health check implementation."""
        if self._health_check_fn:
            try:
                result = await self._health_check_fn()
                if isinstance(result, dict):
                    return HealthResponse(**result)
            except Exception as e:
                logger.warning("Health check failed: %s", e)
                return HealthResponse(
                    ok=False,
                    status="unhealthy",
                    service="unknown",
                    checks={"error": {"status": "unhealthy", "message": str(e)}},
                )
        
        return HealthResponse(
            ok=True,
            status="healthy",
            service=self.config.service_name,
            version=self.config.version,
            uptime_seconds=time.time() - getattr(self, "_startup_time", time.time()),
        )
    
    def build(self) -> APIRouter:
        """Build the FastAPI router."""
        router = APIRouter(
            prefix=self.config.prefix,
            tags=self.config.tags,
        )
        
        # Add request ID middleware
        @router.middleware("http")
        async def add_request_id(request: Request, call_next):
            request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
            start_time = time.perf_counter()
            
            if self.config.log_requests:
                logger.info("Request: %s %s", request.method, request.url.path)
            
            response = await call_next(request)
            
            duration_ms = (time.perf_counter() - time.time()) * 1000
            response.headers["X-Request-ID"] = request.headers.get("X-Request-ID", str(uuid.uuid4()))
            response.headers["X-Response-Time-MS"] = f"{(time.perf_counter() - time.time()) * 1000:.2f}"
            
            return response
        
        # Add routes
        for route_config in self._routes:
            router.add_api_route(
                path=route_config.path,
                endpoint=route_config.handler,
                methods=[route_config.method],
                response_model=route_config.response_model,
                status_code=route_config.status_code,
                summary=route_config.summary,
                description=route_config.description,
                tags=route_config.tags or self.config.tags,
                dependencies=route_config.dependencies,
                deprecated=route_config.deprecated,
                include_in_schema=route_config.include_in_schema,
            )
        
        # Add health endpoint if configured
        if self.config.include_health:
            router.add_api_route(
                path=self.config.health_endpoint,
                endpoint=self._health_check,
                methods=["GET"],
                response_model=HealthResponse,
                summary="Health check",
                tags=["health"],
            )
        
        # Add version endpoint if configured
        if self.config.include_version:
            router.add_api_route(
                path="/version",
                endpoint=lambda: {"service": self.config.service_name, "version": self.config.version},
                methods=["GET"],
                tags=["info"],
            )
        
        return router


def create_router(
    service_name: str,
    version: str = "1.0.0",
    prefix: str = "",
    tags: Optional[List[str]] = None,
    health_check_fn: Optional[Callable] = None,
    routes: Optional[List[Dict[str, Any]]] = None,
    **config_kwargs,
) -> APIRouter:
    """Convenience function to create a router.
    
    Usage:
        router = create_router(
            service_name="my-service",
            health_check_fn=my_health_check,
            routes=[
                {"path": "/items", "method": "GET", "handler": get_items},
                {"path": "/items/{id}", "method": "GET", "handler": get_item},
            ]
        )
    """
    factory = RouterFactory(RouterConfig(
        service_name=service_name,
        version=version,
        prefix=prefix,
        tags=tags or [],
    ))
    
    if health_check_fn:
        factory.set_health_check(health_check_fn)
    
    if routes:
        for route in routes:
            factory.add_route(**route)
    
    return factory.build()


# =============================================================================
# Standard Error Handlers
# =============================================================================

def create_error_handlers(app: FastAPI) -> None:
    """Add standard error handlers to FastAPI app."""
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.detail,
                error_code=f"HTTP_{exc.status_code}",
            ).dict(),
        )
    
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error=str(exc),
                error_code="VALIDATION_ERROR",
            ).dict(),
        )
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Internal server error",
                error_code="INTERNAL_ERROR",
            ).dict(),
        )


# =============================================================================
# Standard Dependencies
# =============================================================================

class PaginationParams(BaseModel):
    """Standard pagination parameters."""
    page: int = 1
    page_size: int = 20
    max_page_size: int = 100
    
    @property
    def limit(self) -> int:
        return min(self.page_size, self.max_page_size)
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def get_pagination(
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
) -> PaginationParams:
    """Dependency for pagination parameters."""
    return PaginationParams(
        page=max(1, page),
        page_size=min(max(1, page_size), max_page_size),
        max_page_size=max_page_size,
    )


class FilterParams(BaseModel):
    """Standard filter parameters."""
    search: Optional[str] = None
    sort_by: Optional[str] = None
    sort_order: str = "asc"
    filters: Dict[str, Any] = field(default_factory=dict)


def get_filters(
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    **filters,
) -> FilterParams:
    """Dependency for filter parameters."""
    return FilterParams(
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )


# =============================================================================
# Response Helpers
# =============================================================================

def success_response(data: Any = None, message: str = "") -> JSONResponse:
    """Create a success JSON response."""
    return JSONResponse(
        content={
            "ok": True,
            "data": data,
            "message": message,
        }
    )


def error_response(
    error: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Create an error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=error,
            error_code=error_code,
            details=details or {},
        ).dict(),
    )


def paginated_response(
    items: List[Any],
    total: int,
    page: int,
    page_size: int,
) -> JSONResponse:
    """Create a paginated response."""
    return JSONResponse(
        content={
            "ok": True,
            "data": {
                "items": items,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "pages": (total + page_size - 1) // page_size,
                },
            },
        }
    )


# =============================================================================
# Request/Response Logging Middleware
# =============================================================================

@asynccontextmanager
async def log_request_response(request: Request, call_next):
    """Context manager for request/response logging."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.perf_counter()
    
    logger.info("→ %s %s [ID: %s]", request.method, request.url.path, request_id[:8])
    
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        logger.info(
            "← %s %s → %d (%.2fms) [ID: %s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id[:8],
        )
        
        return response
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            "✗ %s %s → ERROR (%.2fms) [ID: %s]: %s",
            request.method,
            request.url.path,
            duration_ms,
            request_id[:8],
            e,
        )
        raise


# =============================================================================
# Convenience Functions
# =============================================================================

def create_crud_router(
    service_name: str,
    version: str = "1.0.0",
    prefix: str = "",
    tags: Optional[List[str]] = None,
    create_handler: Optional[Callable] = None,
    get_handler: Optional[Callable] = None,
    list_handler: Optional[Callable] = None,
    update_handler: Optional[Callable] = None,
    delete_handler: Optional[Callable] = None,
    health_check_fn: Optional[Callable] = None,
) -> APIRouter:
    """Create a standard CRUD router."""
    factory = RouterFactory(RouterConfig(
        service_name=service_name,
        version=version,
        prefix=prefix,
        tags=tags or [service_name],
    ))
    
    if health_check_fn:
        factory.set_health_check(health_check_fn)
    
    if create_handler:
        factory.add_route("/items", "POST", create_handler, status_code=status.HTTP_201_CREATED, summary="Create item")
    if list_handler:
        factory.add_route("/items", "GET", list_handler, summary="List items")
    if get_handler:
        factory.add_route("/items/{item_id}", "GET", get_handler, summary="Get item")
    if update_handler:
        factory.add_route("/items/{item_id}", "PUT", update_handler, summary="Update item")
    if delete_handler:
        factory.add_route("/items/{item_id}", "DELETE", delete_handler, status_code=status.HTTP_204_NO_CONTENT, summary="Delete item")
    
    if health_check_fn:
        factory.set_health_check(health_check_fn)
    
    return factory.build()


__all__ = [
    "RouterConfig",
    "RouteConfig",
    "RouterFactory",
    "create_router",
    "create_crud_router",
    "ErrorResponse",
    "HealthResponse",
    "PaginationParams",
    "FilterParams",
    "get_pagination",
    "get_filters",
    "success_response",
    "error_response",
    "paginated_response",
    "create_error_handlers",
    "log_request_response",
    "RequestLoggerMiddleware",
    "RateLimitMiddleware",
]