"""Unified Event Bus for SentryBOT.

Provides a central publish/subscribe mechanism with:
- Priority-based delivery
- Async/sync handler support
- Event filtering and transformation
- Dead letter queue for failed events
- Metrics and monitoring
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Union
from enum import Enum

logger = logging.getLogger("common.event_bus")


class EventPriority(Enum):
    """Event priority levels."""
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Event:
    """Standard event structure."""
    type: str
    payload: Any = None
    source: str = ""
    priority: EventPriority = EventPriority.NORMAL
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.priority, int):
            self.priority = EventPriority(self.priority)
        if isinstance(self.priority, str):
            self.priority = EventPriority[self.priority.upper()]


@dataclass
class Subscription:
    """Event subscription."""
    handler: Callable[[Event], Any]
    event_type: str
    priority: EventPriority = EventPriority.NORMAL
    filter_fn: Optional[Callable[[Event], bool]] = None
    once: bool = False
    subscription_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


class EventBus:
    """Central event bus for publish/subscribe pattern.
    
    Features:
    - Priority-based handler execution
    - Sync and async handler support
    - Event filtering
    - Dead letter queue for failed events
    - Metrics collection
    """
    
    def __init__(
        self,
        max_queue_size: int = 10000,
        dead_letter_max: int = 1000,
        enable_metrics: bool = True,
    ):
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._wildcard_subscriptions: List[Subscription] = []
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._dead_letter: List[Event] = []
        self._dead_letter_max = dead_letter_max
        self._enable_metrics = enable_metrics
        
        self._running = False
        self._dispatch_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # Metrics
        self._metrics = {
            "published": 0,
            "delivered": 0,
            "failed": 0,
            "dead_lettered": 0,
            "queue_full": 0,
        }
        
        self._handler_metrics: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"calls": 0, "errors": 0, "total_time_ms": 0}
        )
    
    async def start(self) -> None:
        """Start the event dispatch loop."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._dispatch_task = asyncio.create_task(self._dispatch_loop())
            logger.info("EventBus started")
    
    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the event dispatch loop."""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            if self._dispatch_task:
                try:
                    await asyncio.wait_for(self._dispatch_task, timeout=timeout)
                except asyncio.TimeoutError:
                    self._dispatch_task.cancel()
                    try:
                        await self._dispatch_task
                    except asyncio.CancelledError:
                        pass
            logger.info("EventBus stopped")
    
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
        priority: EventPriority = EventPriority.NORMAL,
        filter_fn: Optional[Callable[[Event], bool]] = None,
        once: bool = False,
    ) -> str:
        """Subscribe to an event type.
        
        Args:
            event_type: Event type to subscribe to (use "*" for all events)
            handler: Callable that receives Event
            priority: Handler priority (higher runs first)
            filter_fn: Optional filter function
            once: If True, unsubscribe after first match
            
        Returns:
            Subscription ID for later unsubscription
        """
        subscription = Subscription(
            handler=handler,
            event_type=event_type,
            priority=priority,
            filter_fn=filter_fn,
            once=once,
        )
        
        if event_type == "*":
            self._wildcard_subscriptions.append(subscription)
            self._wildcard_subscriptions.sort(key=lambda s: s.priority.value, reverse=True)
        else:
            self._subscriptions[event_type].append(subscription)
            self._subscriptions[event_type].sort(key=lambda s: s.priority.value, reverse=True)
        
        logger.debug("Subscribed to %s: %s", event_type, subscription.subscription_id)
        return subscription.subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe by subscription ID."""
        # Check regular subscriptions
        for event_type, subs in self._subscriptions.items():
            for i, sub in enumerate(subs):
                if sub.subscription_id == subscription_id:
                    subs.pop(i)
                    logger.debug("Unsubscribed %s from %s", subscription_id, event_type)
                    return True
        
        # Check wildcard subscriptions
        for i, sub in enumerate(self._wildcard_subscriptions):
            if sub.subscription_id == subscription_id:
                self._wildcard_subscriptions.pop(i)
                logger.debug("Unsubscribed %s from *", subscription_id)
                return True
        
        return False
    
    def unsubscribe_all(self, event_type: str) -> int:
        """Unsubscribe all handlers for an event type."""
        count = len(self._subscriptions.get(event_type, []))
        if event_type in self._subscriptions:
            del self._subscriptions[event_type]
        return count
    
    async def publish(self, event: Union[Event, str], payload: Any = None, **kwargs) -> int:
        """Publish an event to all subscribers.
        
        Args:
            event: Event object or event type string
            payload: Payload if event is string
            **kwargs: Additional event fields
            
        Returns:
            Number of handlers that will process the event
        """
        if isinstance(event, str):
            event = Event(type=event, payload=payload, **kwargs)
        
        if not self._running:
            logger.warning("EventBus not running, event dropped: %s", event.type)
            return 0
        
        try:
            await self._queue.put(event)
            self._metrics["published"] += 1
            return len(self._get_handlers(event))
        except asyncio.QueueFull:
            self._metrics["queue_full"] += 1
            logger.warning("EventBus queue full, event dropped: %s", event.type)
            return 0
    
    def publish_sync(self, event: Union[Event, str], payload: Any = None, **kwargs) -> int:
        """Synchronous publish (for non-async contexts)."""
        if isinstance(event, str):
            event = Event(type=event, payload=payload, **kwargs)
        
        if not self._running:
            logger.warning("EventBus not running, event dropped: %s", event.type)
            return 0
        
        try:
            self._queue.put_nowait(event)
            self._metrics["published"] += 1
            return len(self._get_handlers(event))
        except asyncio.QueueFull:
            self._metrics["queue_full"] += 1
            logger.warning("EventBus queue full, event dropped: %s", event.type)
            return 0
    
    def _get_handlers(self, event: Event) -> List[Subscription]:
        """Get all matching handlers for an event."""
        handlers = []
        
        # Specific event type handlers
        for sub in self._subscriptions.get(event.type, []):
            if sub.filter_fn is None or sub.filter_fn(event):
                handlers.append(sub)
        
        # Wildcard handlers
        for sub in self._wildcard_subscriptions:
            if sub.filter_fn is None or sub.filter_fn(event):
                handlers.append(sub)
        
        # Sort by priority
        handlers.sort(key=lambda s: s.priority.value, reverse=True)
        return handlers
    
    async def _dispatch_loop(self) -> None:
        """Main event dispatch loop."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch_event(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("EventBus dispatch error: %s", e)
    
    async def _dispatch_event(self, event: Event) -> None:
        """Dispatch event to all matching handlers."""
        handlers = self._get_handlers(event)
        delivered = 0
        
        for sub in handlers:
            start_time = time.perf_counter()
            try:
                result = sub.handler(event)
                if asyncio.iscoroutine(result):
                    await result
                delivered += 1
                
                if sub.once:
                    self.unsubscribe(sub.subscription_id)
                    
            except Exception as e:
                self._metrics["failed"] += 1
                self._handler_metrics[sub.subscription_id]["errors"] += 1
                logger.error("Handler %s error: %s", sub.subscription_id, e)
                
                # Dead letter
                if len(self._dead_letter) < self._dead_letter_max:
                    self._dead_letter.append(event)
                    self._metrics["dead_lettered"] += 1
            finally:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                self._handler_metrics[sub.subscription_id]["calls"] += 1
                self._handler_metrics[sub.subscription_id]["total_time_ms"] += elapsed_ms
        
        self._metrics["delivered"] += delivered
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get event bus metrics."""
        return {
            **self._metrics,
            "queue_size": self._queue.qsize(),
            "subscriptions": sum(len(s) for s in self._subscriptions.values()) + len(self._wildcard_subscriptions),
            "handler_metrics": dict(self._handler_metrics),
        }
    
    def get_dead_letter(self) -> List[Event]:
        """Get dead letter queue."""
        return list(self._dead_letter)
    
    def clear_dead_letter(self) -> int:
        """Clear dead letter queue."""
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count


# Global event bus instance
_global_event_bus: Optional[EventBus] = None
_event_bus_lock = asyncio.Lock()


async def get_event_bus(
    max_queue_size: int = 10000,
    dead_letter_max: int = 1000,
    enable_metrics: bool = True,
) -> EventBus:
    """Get or create global event bus."""
    global _global_event_bus
    async with _event_bus_lock:
        if _global_event_bus is None:
            _global_event_bus = EventBus(
                max_queue_size=max_queue_size,
                dead_letter_max=dead_letter_max,
                enable_metrics=enable_metrics,
            )
            await _global_event_bus.start()
        return _global_event_bus


async def close_event_bus() -> None:
    """Close global event bus."""
    global _global_event_bus
    async with _event_bus_lock:
        if _global_event_bus:
            await _global_event_bus.stop()
            _global_event_bus = None


# Convenience functions
async def publish(event: Union[Event, str], payload: Any = None, **kwargs) -> int:
    """Publish event to global bus."""
    bus = await get_event_bus()
    return await bus.publish(event, payload, **kwargs)


def publish_sync(event: Union[Event, str], payload: Any = None, **kwargs) -> int:
    """Publish event synchronously."""
    try:
        bus = asyncio.run(get_event_bus())
        return bus.publish_sync(event, payload)
    except RuntimeError:
        # No event loop, create temporary bus
        bus = EventBus()
        return bus.publish_sync(event, payload)


def subscribe(
    event_type: str,
    handler: Callable[[Event], Any],
    priority: EventPriority = EventPriority.NORMAL,
    filter_fn: Optional[Callable[[Event], bool]] = None,
    once: bool = False,
) -> str:
    """Subscribe to global bus."""
    try:
        bus = asyncio.run(get_event_bus())
        return bus.subscribe(event_type, handler, priority, filter_fn, once)
    except RuntimeError:
        bus = EventBus()
        return bus.subscribe(event_type, handler, priority, filter_fn, once)