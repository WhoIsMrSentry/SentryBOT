"""Service Base Classes for SentryBOT.

Provides standard base classes for all services:
- ServiceBase: Abstract base class with lifecycle management
- AsyncServiceBase: For async services
- BackgroundTaskMixin: For services with background tasks
"""

from __future__ import annotations

import abc
import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar
from contextlib import contextmanager

logger = logging.getLogger("common.service_base")

T = TypeVar("T", bound="ServiceBase")


class ServiceState(Enum):
    """Service lifecycle states."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ServiceConfig:
    """Base service configuration."""
    name: str = ""
    auto_start: bool = False
    health_check_interval: float = 30.0
    graceful_shutdown_timeout: float = 10.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ServiceError(Exception):
    """Base service exception."""
    pass


class ServiceNotRunningError(ServiceError):
    """Service is not running."""
    pass


class ServiceAlreadyRunningError(ServiceError):
    """Service is already running."""
    pass


class ServiceTimeoutError(ServiceError):
    """Service operation timed out."""
    pass


class ServiceBase(abc.ABC):
    """Abstract base class for all services.
    
    Provides:
    - Standard lifecycle management (start/stop/restart)
    - Health checks
    - State management
    - Configuration management
    - Graceful shutdown
    - Thread safety
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = ""):
        self._config = ServiceConfig(
            name=name or self.__class__.__name__,
            **(config or {})
        )
        self._state = ServiceState.UNINITIALIZED
        self._state_lock = threading.RLock()
        self._start_time: Optional[float] = None
        self._stop_event = threading.Event()
        self._error: Optional[Exception] = None
        self._health_check_task: Optional[threading.Thread] = None
        self._health_check_interval = self._config.health_check_interval
        self._graceful_shutdown_timeout = self._config.graceful_shutdown_timeout
        self._init_lock = threading.Lock()
        self._initialized = False
        self._shutdown_callbacks: List[Callable[[], None]] = []
    
    @property
    def name(self) -> str:
        return self._config.name
    
    @property
    def config(self) -> ServiceConfig:
        return self._config
    
    @property
    def state(self) -> ServiceState:
        with self._state_lock:
            return self._state
    
    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._state == ServiceState.RUNNING
    
    @property
    def is_stopped(self) -> bool:
        with self._state_lock:
            return self._state == ServiceState.STOPPED
    
    @property
    def uptime(self) -> Optional[float]:
        with self._state_lock:
            if self._start_time is None:
                return None
            return time.time() - self._start_time
    
    @property
    def error(self) -> Optional[Exception]:
        with self._state_lock:
            return self._error
    
    def _set_state(self, state: ServiceState, error: Optional[Exception] = None) -> None:
        with self._state_lock:
            old_state = self._state
            self._state = state
            if error:
                self._error = error
            logger.debug("Service %s state: %s -> %s", self.name, old_state.value, state.value)
    
    def initialize(self) -> None:
        """Initialize the service (called before start)."""
        with self._init_lock:
            if self._initialized:
                logger.debug("Service %s already initialized", self.name)
                return
            
            self._set_state(ServiceState.INITIALIZING)
            try:
                self._do_initialize()
                self._initialized = True
                self._set_state(ServiceState.STOPPED)
                logger.info("Service %s initialized", self.name)
            except Exception as e:
                self._set_state(ServiceState.ERROR, e)
                logger.exception("Service %s initialization failed: %s", self.name, e)
                raise
    
    @abc.abstractmethod
    def _do_initialize(self) -> None:
        """Subclass-specific initialization."""
        pass
    
    def start(self) -> None:
        """Start the service."""
        with self._state_lock:
            if self._state == ServiceState.RUNNING:
                logger.warning("Service %s already running", self.name)
                return
            if self._state == ServiceState.STARTING:
                raise ServiceAlreadyRunningError(f"Service {self.name} is starting")
        
        self._set_state(ServiceState.STARTING)
        try:
            if not self._initialized:
                self.initialize()
            
            self._stop_event.clear()
            self._do_start()
            self._start_time = time.time()
            self._set_state(ServiceState.RUNNING)
            self._start_health_check()
            logger.info("Service %s started", self.name)
        except Exception as e:
            self._set_state(ServiceState.ERROR, e)
            logger.exception("Service %s start failed: %s", self.name, e)
            raise
    
    @abc.abstractmethod
    def _do_start(self) -> None:
        """Subclass-specific start logic."""
        pass
    
    def stop(self, timeout: Optional[float] = None) -> None:
        """Stop the service gracefully."""
        with self._state_lock:
            if self._state not in (ServiceState.RUNNING, ServiceState.STARTING):
                logger.warning("Service %s not running, state: %s", self.name, self._state.value)
                return
        
        timeout = timeout or self._graceful_shutdown_timeout
        self._set_state(ServiceState.STOPPING)
        
        try:
            self._stop_event.set()
            self._do_stop(timeout)
            self._stop_health_check()
            self._set_state(ServiceState.STOPPED)
            self._start_time = None
            logger.info("Service %s stopped", self.name)
        except Exception as e:
            self._set_state(ServiceState.ERROR, e)
            logger.exception("Service %s stop failed: %s", self.name, e)
            raise
        finally:
            self._run_shutdown_callbacks()
    
    @abc.abstractmethod
    def _do_stop(self, timeout: float) -> None:
        """Subclass-specific stop logic."""
        pass
    
    def restart(self, timeout: Optional[float] = None) -> None:
        """Restart the service."""
        timeout = timeout or self._config.graceful_shutdown_timeout
        self.stop(timeout)
        self.start()
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check.
        
        Returns:
            Dict with health status and details.
        """
        with self._state_lock:
            status = "healthy" if self._state == ServiceState.RUNNING else "unhealthy"
            return {
                "name": self.name,
                "state": self._state.value,
                "status": status,
                "uptime": self.uptime,
                "error": str(self._error) if self._error else None,
            }
    
    def _start_health_check(self) -> None:
        if self._health_check_interval <= 0:
            return
        self._health_check_task = threading.Thread(
            target=self._health_check_loop,
            name=f"{self.name}-health-check",
            daemon=True,
        )
        self._health_check_task.start()
    
    def _stop_health_check(self) -> None:
        pass  # Thread is daemon, will exit when main exits
    
    def _health_check_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self._health_check_interval)
            if self._stop_event.is_set():
                break
            try:
                health = self.health_check()
                if health.get("status") != "healthy":
                    logger.warning("Service %s health check failed: %s", self.name, health)
            except Exception as e:
                logger.error("Health check failed for %s: %s", self.name, e)
    
    def add_shutdown_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback to run on shutdown."""
        self._shutdown_callbacks.append(callback)
    
    def _run_shutdown_callbacks(self) -> None:
        for callback in self._shutdown_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("Shutdown callback failed: %s", e)
    
    def __enter__(self) -> "ServiceBase":
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


class AsyncServiceBase(abc.ABC):
    """Abstract base class for async services."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = ""):
        self._config = ServiceConfig(name=name or self.__class__.__name__, **(config or {}))
        self._state = ServiceState.UNINITIALIZED
        self._state_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._error: Optional[Exception] = None
        self._start_time: Optional[float] = None
        self._initialized = False
        self._shutdown_callbacks: List[Callable[[], Any]] = []
    
    @property
    def name(self) -> str:
        return self._config.name
    
    @property
    def config(self) -> ServiceConfig:
        return self._config
    
    @property
    def state(self) -> ServiceState:
        return self._state
    
    @property
    def is_running(self) -> bool:
        return self._state == ServiceState.RUNNING
    
    @property
    def uptime(self) -> Optional[float]:
        if self._start_time is None:
            return None
        return time.time() - self._start_time
    
    def _set_state(self, state: ServiceState, error: Optional[Exception] = None) -> None:
        self._state = state
        if error:
            self._error = error
        logger.debug("AsyncService %s state: %s", self.name, state.value)
    
    async def initialize(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._state = ServiceState.INITIALIZING
        try:
            await self._do_initialize()
            self._initialized = True
            logger.info("AsyncService %s initialized", self.name)
        except Exception as e:
            self._state = ServiceState.ERROR
            logger.exception("AsyncService %s initialization failed: %s", self.name, e)
            raise
    
    @abc.abstractmethod
    async def _do_initialize(self) -> None:
        pass
    
    async def start(self) -> None:
        if self._state == ServiceState.RUNNING:
            logger.warning("AsyncService %s already running", self.name)
            return
        
        if not getattr(self, "_initialized", False):
            await self.initialize()
        
        self._state = ServiceState.STARTING
        try:
            await self._do_start()
            self._start_time = time.time()
            self._state = ServiceState.RUNNING
            logger.info("AsyncService %s started", self.name)
        except Exception as e:
            self._state = ServiceState.ERROR
            logger.exception("AsyncService %s start failed: %s", self.name, e)
            raise
    
    @abc.abstractmethod
    async def _do_start(self) -> None:
        pass
    
    async def stop(self, timeout: Optional[float] = None) -> None:
        if self._state not in (ServiceState.RUNNING, ServiceState.STARTING):
            logger.warning("AsyncService %s not running", self.name)
            return
        
        self._state = ServiceState.STOPPING
        try:
            await self._do_stop(timeout or 10.0)
            self._state = ServiceState.STOPPED
            logger.info("AsyncService %s stopped", self.name)
        except Exception as e:
            self._state = ServiceState.ERROR
            logger.exception("AsyncService %s stop failed: %s", self.name, e)
            raise
    
    @abc.abstractmethod
    async def _do_stop(self, timeout: float) -> None:
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.value,
            "status": "healthy" if self._state == ServiceState.RUNNING else "unhealthy",
            "uptime": time.time() - self._start_time if self._start_time else None,
            "error": str(self._error) if hasattr(self, '_error') and self._error else None,
        }
    
    async def __aenter__(self) -> "AsyncServiceBase":
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()


class BackgroundTaskMixin:
    """Mixin for services that run background tasks."""
    
    def __init__(self):
        self._background_tasks: Set[asyncio.Task] = set()
        self._task_lock = asyncio.Lock()
    
    async def create_background_task(
        self,
        coro,
        name: str = "",
        restart: bool = False,
        restart_delay: float = 1.0,
    ) -> asyncio.Task:
        """Create and track a background task."""
        async def wrapped():
            while True:
                try:
                    await coro
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("Background task %s error: %s", name, e)
                    if not self._stop_event.is_set():
                        await asyncio.sleep(1)
                        if restart:
                            continue
                break
        
        task = asyncio.create_task(wrapped(), name=name or coro.__name__)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task
    
    async def cancel_background_tasks(self) -> None:
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
    
    @property
    def background_tasks(self) -> Set[asyncio.Task]:
        return self._background_tasks.copy()


__all__ = [
    "ServiceBase",
    "AsyncServiceBase",
    "BackgroundTaskMixin",
    "ServiceConfig",
    "ServiceState",
    "ServiceError",
    "ServiceNotRunningError",
    "ServiceAlreadyRunningError",
    "ServiceTimeoutError",
]