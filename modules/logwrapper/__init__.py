"""
logwrapper modülü: merkezi loglama altyapısı.

Dışa açılan basit API:
- init_logging(overrides: dict | None) -> None
- get_memory_handler() -> InMemoryLogHandler | None
- get_router() -> fastapi.APIRouter (opsiyonel)
"""
from .xLogService import init_logging, get_memory_handler, get_router

__all__ = [
    "init_logging",
    "get_memory_handler",
    "get_router",
]
