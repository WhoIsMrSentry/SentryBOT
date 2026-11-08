from __future__ import annotations

from typing import Any, Optional
import httpx

from modules.common.command_registry import (  # type: ignore
    CommandResult,
    get_command_registry,
)


class _PhotoCaptureClient:
    """Thin proxy forwarding HTTP requests while retaining captured snapshot bytes."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self.last_photo: bytes | None = None

    async def get(self, url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        resp = await self._client.get(url, *args, **kwargs)
        if resp.status_code == 200 and resp.content:
            ctype = str(resp.headers.get("content-type", "")).lower()
            if ctype.startswith("image/") or url.rstrip("/").endswith("/snap"):
                self.last_photo = resp.content
        return resp

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def _safe_int(value: int | str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class CommandRouter:
    """Map Telegram commands to HTTP calls on other modules via unified CommandRegistry."""

    def __init__(self, base_url: str, timeout: float = 4.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._registry = get_command_registry(self._base, self._timeout)
        self._registry.set_base_url(self._base)
        self._registry.set_timeout(self._timeout)
        self._registry.set_services({"gateway_base_url": self._base})

    def set_http_client(self, client: httpx.AsyncClient | None) -> None:
        """Set shared HTTP client for all command handlers."""
        self._registry.set_http_client(client)

    async def handle(
        self,
        client: httpx.AsyncClient | None,
        text: str,
        *,
        user_id: int = 0,
        chat_id: int | str = 0,
    ) -> Optional[CommandResult]:
        """Handle a command text and return a CommandResult."""
        capture: _PhotoCaptureClient | None = None
        if client is not None:
            capture = _PhotoCaptureClient(client)
            self._registry.set_http_client(capture)
            self._registry.set_services({"gateway_base_url": self._base, "_http_client": capture})
        else:
            self._registry.set_http_client(None)
            self._registry.set_services({"gateway_base_url": self._base})

        result_text = await self._registry.handle(
            text,
            user_id=int(user_id),
            chat_id=_safe_int(chat_id),
        )
        if result_text is None:
            return None

        if result_text.startswith("[PHOTO]"):
            caption = result_text[7:].strip()
            if capture and capture.last_photo:
                return CommandResult(photo=capture.last_photo, photo_caption=caption or None)
            return CommandResult(text=caption or "Snapshot")

        return CommandResult(text=result_text)

    def set_base_url(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        self._registry.set_base_url(self._base)

    def set_timeout(self, timeout: float) -> None:
        self._timeout = timeout
        self._registry.set_timeout(self._timeout)

    def register_custom_command(self, handler: Any) -> None:
        """Register a custom command handler."""
        self._registry.register(handler)

    def get_help_text(self, admin: bool = False) -> str:
        return self._registry.get_help_text(admin)


__all__ = [
    "CommandResult",
    "CommandRouter",
]