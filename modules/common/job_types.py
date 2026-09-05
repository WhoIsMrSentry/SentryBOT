"""Scheduler Job Types Plugin Registry for SentryBOT.

Provides a plugin system for job types to replace hardcoded if/elif chains
in scheduler with extensible registry pattern.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union
from uuid import uuid4

logger = logging.getLogger("common.job_types")


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class JobResult:
    """Result of a job execution."""
    job_id: str
    status: JobStatus
    started_at: float
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> Optional[float]:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at) * 1000
        return None


@dataclass
class JobDefinition:
    """Job definition (immutable configuration)."""
    id: str
    kind: str
    name: str = ""
    description: str = ""
    enabled: bool = True
    
    # Scheduling
    every_s: Optional[float] = None  # Interval in seconds
    cron: Optional[str] = None       # Cron expression (requires croniter)
    start_at: Optional[float] = None # Unix timestamp for first run
    max_runs: Optional[int] = None   # Maximum number of runs
    
    # Execution
    timeout_s: float = 30.0
    max_retries: int = 0
    retry_delay_s: float = 5.0
    max_instances: int = 1
    
    # Parameters passed to job handler
    params: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())
        if not self.name:
            self.name = self.kind


class JobContext:
    """Context provided to job handlers during execution."""
    
    def __init__(self, job: JobDefinition, services: Dict[str, Any]):
        self.job = job
        self.services = services
        self.run_id = str(uuid4())
        self.started_at = time.time()
        self.attempt = 0
        self._cancelled = False
        self._metadata: Dict[str, Any] = {}
    
    @property
    def cancelled(self) -> bool:
        return self._cancelled
    
    def cancel(self) -> None:
        self._cancelled = True
    
    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)


class JobHandler(ABC):
    """Abstract base class for job handlers."""
    
    @property
    @abstractmethod
    def kind(self) -> str:
        """Unique job kind identifier."""
        pass
    
    @property
    def description(self) -> str:
        return f"Job handler for {self.kind}"
    
    @property
    def default_timeout(self) -> float:
        return 30.0
    
    @property
    def supports_concurrent(self) -> bool:
        """Whether multiple instances can run concurrently."""
        return False
    
    @abstractmethod
    async def execute(self, context: JobContext) -> Any:
        """Execute the job.
        
        Args:
            context: Job execution context with parameters and services
            
        Returns:
            Job result (will be stored in JobResult.result)
        """
        pass
    
    async def on_start(self, context: JobContext) -> None:
        """Called before job execution starts."""
        pass
    
    async def on_complete(self, context: JobContext, result: Any) -> None:
        """Called after successful completion."""
        pass
    
    async def on_error(self, context: JobContext, error: Exception) -> None:
        """Called when job fails."""
        pass
    
    async def on_cancel(self, context: JobContext) -> None:
        """Called when job is cancelled."""
        pass
    
    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate job parameters. Return (is_valid, error_message)."""
        return True, None


# =============================================================================
# Built-in Job Handlers
# =============================================================================

class HTTPJobHandler(JobHandler):
    """Handler for HTTP request jobs."""
    
    kind = "http"
    
    def __init__(self, default_session=None):
        self._default_session = default_session
    
    async def execute(self, context: JobContext) -> Any:
        import aiohttp
        
        params = context.job.params
        method = params.get("method", "GET").upper()
        url = params.get("url") or context.services.get("gateway_base_url", "") + params.get("path", "")
        
        if not url:
            raise ValueError("HTTP job requires 'url' or 'path' parameter")
        
        headers = params.get("headers", {})
        body = params.get("body")
        json_body = params.get("json")
        timeout = context.job.timeout_s
        
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url,
                headers=headers,
                data=body,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                result = {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                }
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    result["json"] = await resp.json()
                else:
                    result["text"] = await resp.text()
                return result
    
    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if not params.get("url") and not params.get("path"):
            return False, "HTTP job requires 'url' or 'path' parameter"
        return True, None


class SpeakJobHandler(JobHandler):
    """Handler for TTS speak jobs."""
    
    kind = "speak"
    
    async def execute(self, context: JobContext) -> Any:
        speak_service = context.services.get("speak")
        if not speak_service:
            raise RuntimeError("Speak service not available")
        
        params = context.job.params
        text = params.get("text", "")
        engine = params.get("engine")
        tone = params.get("tone")
        language = params.get("language")
        streaming = params.get("streaming", False)
        
        if not text:
            raise ValueError("Speak job requires 'text' parameter")
        
        if streaming:
            # For streaming, return job ID for polling
            job_id = await speak_service.say_stream(text=text, engine=engine, tone=tone, language=language)
            return {"job_id": job_id, "streaming": True}
        else:
            result = await speak_service.say(text=text, engine=engine, tone=tone, language=language)
            return {"result": result}
    
    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if not params.get("text"):
            return False, "Speak job requires 'text' parameter"
        return True, None


class InteractionEventHandler(JobHandler):
    """Handler for interaction event jobs."""
    
    kind = "interaction_event"
    
    async def execute(self, context: JobContext) -> Any:
        interactions_service = context.services.get("interactions")
        if not interactions_service:
            raise RuntimeError("Interactions service not available")
        
        params = context.job.params
        event_type = params.get("type", "")
        data = params.get("data", {})
        
        if not event_type:
            raise ValueError("Interaction event requires 'type' parameter")
        
        await interactions_service.push_event(event_type, data)
        return {"event": event_type, "pushed": True}
    
    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if not params.get("type"):
            return False, "Interaction event requires 'type' parameter"
        return True, None


class DiagnosticsJobHandler(JobHandler):
    """Handler for diagnostics run jobs."""
    
    kind = "diagnostics"
    
    async def execute(self, context: JobContext) -> Any:
        diagnostics_service = context.services.get("diagnostics")
        if not diagnostics_service:
            raise RuntimeError("Diagnostics service not available")
        
        report = await diagnostics_service.run_checks()
        return {"report": report}


class StateSetHandler(JobHandler):
    """Handler for state set jobs."""
    
    kind = "state_set"
    
    async def execute(self, context: JobContext) -> Any:
        state_manager = context.services.get("state_manager")
        if not state_manager:
            raise RuntimeError("State manager not available")
        
        params = context.job.params
        key = params.get("key", "")
        value = params.get("value")
        
        if not key:
            raise ValueError("State set job requires 'key' parameter")
        
        await state_manager.set(key, value)
        return {"key": key, "value": value, "set": True}


class NotifyHandler(JobHandler):
    """Handler for notification jobs."""
    
    kind = "notify"
    
    async def execute(self, context: JobContext) -> Any:
        notifier_service = context.services.get("notifier")
        if not notifier_service:
            raise RuntimeError("Notifier service not available")
        
        params = context.job.params
        text = params.get("text", "")
        channel = params.get("channel", "telegram")
        
        if not text:
            raise ValueError("Notify job requires 'text' parameter")
        
        result = await notifier_service.send(text=text, channel=channel)
        return {"sent": True, "channel": channel}


# =============================================================================
# Job Registry
# =============================================================================

class JobRegistry:
    """Registry for job handlers with plugin support."""
    
    def __init__(self):
        self._handlers: Dict[str, Type[JobHandler]] = {}
        self._instances: Dict[str, JobHandler] = {}
        self._services: Dict[str, Any] = {}
    
    def register(self, handler_class: Type[JobHandler], **kwargs) -> None:
        """Register a job handler class."""
        if not issubclass(handler_class, JobHandler):
            raise TypeError(f"{handler_class} must be a JobHandler subclass")
        
        instance = handler_class(**kwargs)
        kind = instance.kind
        
        if kind in self._handlers:
            logger.warning("Overriding existing handler for kind: %s", kind)
        
        self._handlers[kind] = handler_class
        self._instances[kind] = instance
        logger.info("Registered job handler: %s", kind)
    
    def unregister(self, kind: str) -> bool:
        """Unregister a job handler."""
        if kind in self._handlers:
            del self._handlers[kind]
            if kind in self._instances:
                del self._instances[kind]
            return True
        return False
    
    def get(self, kind: str) -> Optional[JobHandler]:
        """Get handler instance for a kind."""
        return self._instances.get(kind)
    
    def get_class(self, kind: str) -> Optional[Type[JobHandler]]:
        """Get handler class for a kind."""
        return self._handlers.get(kind)
    
    def get_all_kinds(self) -> List[str]:
        return list(self._handlers.keys())
    
    def set_services(self, services: Dict[str, Any]) -> None:
        """Set services available to job handlers."""
        self._services = services
    
    def create_context(self, job: JobDefinition) -> JobContext:
        """Create job context with services."""
        return JobContext(job, self._services.copy())


# Global registry instance
_global_registry: Optional[JobRegistry] = None
_registry_lock = asyncio.Lock()


def get_job_registry() -> JobRegistry:
    """Get global job registry."""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:
                _global_registry = JobRegistry()
                # Register built-in handlers
                _global_registry.register(HTTPJobHandler)
                _global_registry.register(SpeakJobHandler)
                _global_registry.register(InteractionEventHandler)
                _global_registry.register(DiagnosticsJobHandler)
                _global_registry.register(StateSetHandler)
                _global_registry.register(NotifyHandler)
    return _global_registry


async def get_job_registry_async() -> JobRegistry:
    """Async version for async contexts."""
    async with _registry_lock:
        if _global_registry is None:
            _global_registry = JobRegistry()
            _global_registry.register(HTTPJobHandler)
            _global_registry.register(SpeakJobHandler)
            _global_registry.register(InteractionEventHandler)
            _global_registry.register(DiagnosticsJobHandler)
            _global_registry.register(StateSetHandler)
            _global_registry.register(NotifyHandler)
    return _global_registry


def register_job_handler(handler_class: Type[JobHandler], **kwargs) -> None:
    """Register a job handler (sync)."""
    registry = get_job_registry()
    registry.register(handler_class, **kwargs)


async def register_job_handler_async(handler_class: Type[JobHandler], **kwargs) -> None:
    """Register a job handler (async)."""
    registry = await get_job_registry_async()
    registry.register(handler_class, **kwargs)


def get_job_handler(kind: str) -> Optional[JobHandler]:
    """Get job handler by kind."""
    registry = get_job_registry()
    return registry.get(kind)


def get_job_handler_class(kind: str) -> Optional[Type[JobHandler]]:
    """Get job handler class by kind."""
    registry = get_job_registry()
    return registry.get_class(kind)


__all__ = [
    "JobStatus",
    "JobResult",
    "JobDefinition",
    "JobContext",
    "JobHandler",
    "JobRegistry",
    "get_job_registry",
    "get_job_registry_async",
    "register_job_handler",
    "register_job_handler_async",
    "get_job_handler",
    "get_job_handler_class",
    # Built-in handlers
    "HTTPJobHandler",
    "SpeakJobHandler",
    "InteractionEventHandler",
    "DiagnosticsJobHandler",
    "StateSetHandler",
    "NotifyHandler",
]