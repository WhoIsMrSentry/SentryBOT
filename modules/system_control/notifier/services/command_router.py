from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import httpx

from modules.common.command_registry import (  # type: ignore
    CommandRegistry,
    CommandResult,
    CommandContext,
    get_command_registry,
)


@dataclass
class CommandRouter:
    """Map Telegram commands to HTTP calls on other modules.
    
    Now uses the unified CommandRegistry from modules.common for
    extensible plugin-based command handling.
    """

    def __init__(self, base_url: str, timeout: float = 4.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        
        # Initialize unified command registry
        self._registry = get_command_registry(base_url, timeout)
        self._registry.set_services({
            "gateway_base_url": self._base,
        })
    
    def set_http_client(self, client: httpx.AsyncClient) -> None:
        """Set shared HTTP client for all command handlers."""
        self._registry._http_client = client
    
    async def handle(self, client: httpx.AsyncClient, text: str) -> Optional[CommandResult]:
        """Handle a command text and return response."""
        # Use the unified registry
        result_text = await self._registry.handle(text, client=client)
        
        if result_text is None:
            return None
        
        if result_text.startswith("[PHOTO]"):
            # Photo response
            caption = result_text[7:]  # Remove [PHOTO] prefix
            return CommandResult(photo=client.get_photo_cache(), photo_caption=caption)
        
        return CommandResult(text=result_text)
    
    def set_base_url(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        self._registry.set_base_url(self._base)
    
    def set_timeout(self, timeout: float) -> None:
        self._timeout = timeout
        self._registry.set_timeout(self._timeout)
    
    def register_custom_command(self, handler) -> None:
        """Register a custom command handler."""
        self._registry.register(handler)
    
    def get_help_text(self, admin: bool = False) -> str:
        return self._registry.get_help_text(admin)


# Backward compatibility - old interface
class CommandRouterLegacy:
    """Legacy command router for backward compatibility."""
    
    def __init__(self, base_url: str, timeout: float = 4.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._registry = get_command_registry(base_url, timeout)
        self._registry.set_services({"gateway_base_url": self._base})
    
    async def handle(self, client: httpx.AsyncClient, text: str) -> Optional[CommandResult]:
        result_text = await self._registry.handle(text, client=client)
        
        if result_text is None:
            return None
        
        if result_text.startswith("[PHOTO]"):
            return CommandResult(photo=bytes(), photo_caption=result_text[7:])
        
        return CommandResult(text=result_text)


# For backward compatibility - export the old class name
CommandRouter = CommandRouterLegacy

__all__ = [
    "CommandResult",
    "CommandRouter",
]