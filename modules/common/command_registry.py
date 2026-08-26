"""Command Registry for SentryBOT Telegram/Discord Commands.

Provides a plugin system for command handlers to replace hardcoded
if/elif chains in CommandRouter with extensible registry pattern.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Pattern, Type

logger = logging.getLogger("common.command_registry")


@dataclass
class CommandResult:
    """Result of a command execution."""
    text: Optional[str] = None
    photo: Optional[bytes] = None
    photo_caption: Optional[str] = None
    reply_markup: Optional[Dict[str, Any]] = None


@dataclass
class CommandContext:
    """Context provided to command handlers."""
    args: List[str]
    raw_text: str
    user_id: int
    username: Optional[str] = None
    chat_id: int = 0
    services: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CommandHandler(ABC):
    """Abstract base class for command handlers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique command name (e.g., 'status', 'snap')."""
        pass
    
    @property
    def aliases(self) -> List[str]:
        """Alternative names/aliases for this command."""
        return []
    
    @property
    def description(self) -> str:
        return f"Command: {self.name}"
    
    @property
    def usage(self) -> str:
        """Usage string for help."""
        return f"/{self.name}"
    
    @property
    def admin_only(self) -> bool:
        """Whether this command requires admin privileges."""
        return False
    
    @property
    def hidden(self) -> bool:
        """Whether to hide from help."""
        return False
    
    @abstractmethod
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        """Execute the command.
        
        Args:
            context: Command execution context
            
        Returns:
            CommandResult or None if command wasn't matched
        """
        pass
    
    def matches(self, text: str) -> bool:
        """Check if this handler matches the command text."""
        command = text.strip().split()[0].lower() if text.strip() else ""
        names = [self.name] + self.aliases
        return command in [n.lstrip("/") for n in names]
    
    def validate_args(self, args: List[str]) -> tuple[bool, Optional[str]]:
        """Validate command arguments. Return (is_valid, error_message)."""
        return True, None
    
    def get_help(self) -> str:
        """Get help text for this command."""
        return f"/{self.name} - {self.description}"




# =============================================================================
# Built-in Command Handlers
# =============================================================================

class HelpCommandHandler:
    """Built-in help command."""
    
    name = "help"
    aliases = ["h", "?"]
    description = "Bu yardım mesajını göster"
    usage = "/help"
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        registry = context.services.get("_command_registry")
        if registry:
            admin = False  # Check admin in real implementation
            return CommandResult(text=registry.get_help_text(admin))
        return CommandResult(text="Yardım bulunamadı")


class StatusCommandHandler:
    name = "status"
    description = "Sistem modül sağlık kontrolü"
    usage = "/status"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/health"
            resp = await client.get(url, timeout=self._timeout)
            if resp.status_code != 200:
                return CommandResult(text=f"Status error: {resp.status_code}")
            
            data = resp.json()
            mods = data if isinstance(data, dict) else {}
            summary = []
            for name, info in mods.items():
                if name == "ok":
                    continue
                ok = info.get("ok", False) if isinstance(info, dict) else False
                summary.append(f"{name}:{'ok' if ok else 'fail'}")
            
            status = "ok" if mods.get("ok", False) else "fail"
            return CommandResult(text=f"Durum {status} " + ", ".join(summary))
        except Exception as exc:
            return CommandResult(text=f"Status hata: {exc}")
        finally:
            if close_client:
                await client.aclose()


class SnapCommandHandler:
    name = "snap"
    aliases = ["snapshot"]
    description = "Kamera fotoğrafı gönder"
    usage = "/snap"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/camera/snap"
            resp = await client.get(url, timeout=self._timeout)
            if resp.status_code != 200:
                return CommandResult(text=f"Snapshot hata: {resp.status_code}")
            return CommandResult(photo=resp.content, photo_caption="📸 Snapshot")
        except Exception as exc:
            return CommandResult(text=f"Snapshot hata: {exc}")
        finally:
            if close_client:
                await client.aclose()


class PanTiltCommandHandler:
    name = "pt"
    aliases = ["track"]
    description = "Kafa pan/tilt hareket ettir"
    usage = "/pt <pan> <tilt>"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        args = context.args
        if len(args) < 2:
            return CommandResult(text="Kullanım: /pt <pan> <tilt> (derece)")
        
        try:
            pan = float(args[0])
            tilt = float(args[1])
        except (ValueError, IndexError):
            return CommandResult(text="Kullanım: /pt <pan> <tilt>")
        
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/vlm/track"
            params = {"head_pan": pan, "head_tilt": tilt}
            resp = await client.post(url, params=params, timeout=self._timeout)
            ok = resp.status_code == 200
            if close_client:
                await client.aclose()
            return CommandResult(text="Pan/tilt ok" if ok else "Pan/tilt başarısız")
        except Exception as exc:
            if close_client:
                await client.aclose()
            return CommandResult(text=f"Pan/tilt hata: {exc}")


class PanCommandHandler:
    name = "pan"
    description = "Sadece pan (yaw) ayarla"
    usage = "/pan <derece>"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        args = context.args
        if not args:
            return CommandResult(text="Kullanım: /pan <derece>")
        
        try:
            pan = float(args[0])
        except ValueError:
            return CommandResult(text="Kullanım: /pan <derece>")
        
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/vlm/track"
            params = {"head_pan": pan, "head_tilt": 0.0}
            resp = await client.post(url, params=params, timeout=self._timeout)
            ok = resp.status_code == 200
            if close_client:
                await client.aclose()
            return CommandResult(text="Pan ok" if ok else "Pan başarısız")
        except Exception as exc:
            if close_client:
                await client.aclose()
            return CommandResult(text=f"Pan hata: {exc}")


class TiltCommandHandler:
    name = "tilt"
    description = "Sadece tilt (pitch) ayarla"
    usage = "/tilt <derece>"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        args = context.args
        if not args:
            return CommandResult(text="Kullanım: /tilt <derece>")
        
        try:
            tilt = float(args[0])
        except ValueError:
            return CommandResult(text="Kullanım: /tilt <derece>")
        
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/vlm/track"
            params = {"head_pan": 0.0, "head_tilt": tilt}
            resp = await client.post(url, params=params, timeout=self._timeout)
            ok = resp.status_code == 200
            if close_client:
                await client.aclose()
            return CommandResult(text="Tilt ok" if ok else "Tilt başarısız")
        except Exception as exc:
            if close_client:
                await client.aclose()
            return CommandResult(text=f"Tilt hata: {exc}")


class NeoFillCommandHandler:
    name = "neofill"
    aliases = ["fill"]
    description = "Tüm LED'leri tek renkle doldur"
    usage = "/neofill <r> <g> <b>"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        args = context.args
        if len(args) < 3:
            return CommandResult(text="Kullanım: /neofill <r> <g> <b>")
        
        try:
            r, g, b = [int(x) for x in args[:3]]
        except ValueError:
            return CommandResult(text="Kullanım: /neofill <r> <g> <b>")
        
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/neopixel/fill"
            params = {"r_": r, "g": g, "b": b}
            resp = await client.post(url, params=params, timeout=self._timeout)
            ok = resp.status_code == 200
            if close_client:
                await client.aclose()
            return CommandResult(text="NeoPixel set" if ok else "NeoPixel hata")
        except Exception as exc:
            if close_client:
                await client.aclose()
            return CommandResult(text=f"NeoPixel hata: {exc}")


class NeoClearCommandHandler:
    name = "neoclear"
    aliases = ["clear"]
    description = "LED'leri temizle (kapat)"
    usage = "/neoclear"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/neopixel/clear"
            resp = await client.post(url, timeout=self._timeout)
            ok = resp.status_code == 200
            if close_client:
                await client.aclose()
            return CommandResult(text="NeoPixel cleared" if ok else "NeoPixel clear hata")
        except Exception as exc:
            if close_client:
                await client.aclose()
            return CommandResult(text=f"NeoPixel clear hata: {exc}")


class SayCommandHandler:
    name = "say"
    aliases = ["tts"]
    description = "Metni seslendir (TTS)"
    usage = "/say <metin>"
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 15.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
    
    async def execute(self, context: CommandContext) -> Optional[CommandResult]:
        text = " ".join(context.args).strip()
        if not text:
            return CommandResult(text="Kullanım: /say <metin>")
        
        import httpx
        client = context.services.get("_http_client")
        if not client:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True
        else:
            close_client = False
        
        try:
            url = f"{self._base_url}/speak/say"
            resp = await client.post(url, json={"text": text}, timeout=self._timeout)
            if resp.status_code != 200:
                return CommandResult(text=f"TTS http {resp.status_code}")
            
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
            if isinstance(data, dict) and data.get("ok"):
                return CommandResult(text="TTS oynatılıyor")
            err = data.get("error") if isinstance(data, dict) else data
            return CommandResult(text=f"TTS hata: {err}")
        except Exception as exc:
            if close_client:
                await client.aclose()
            return CommandResult(text=f"TTS istek hatası: {exc!r}")
        finally:
            if close_client:
                await client.aclose()




# =============================================================================
# Registry
# =============================================================================

class CommandRegistry:
    """Registry for command handlers with plugin support."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._handlers: Dict[str, Any] = {}
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._services: Dict[str, Any] = {}
        self._http_client = None
        
        # Register built-in handlers
        self._register_builtins()
    
    def _register_builtins(self):
        """Register built-in command handlers."""
        self.register(HelpCommandHandler())
        self.register(StatusCommandHandler(self._base_url, self._timeout))
        self.register(SnapCommandHandler(self._base_url, self._timeout))
        self.register(PanTiltCommandHandler(self._base_url, self._timeout))
        self.register(PanCommandHandler(self._base_url, self._timeout))
        self.register(TiltCommandHandler(self._base_url, self._timeout))
        self.register(NeoFillCommandHandler(self._base_url, self._timeout))
        self.register(NeoClearCommandHandler(self._base_url, self._timeout))
        self.register(SayCommandHandler(self._base_url, self._timeout))
    
    def register(self, handler: Any) -> None:
        """Register a command handler."""
        name = handler.name
        if name in self._handlers:
            logger.warning("Overriding existing handler for command: %s", name)
        
        self._handlers[name] = handler
        
        for alias in getattr(handler, "aliases", []):
            if alias in self._handlers:
                logger.warning("Overriding existing alias: %s", alias)
            self._handlers[alias] = handler
        
        logger.info("Registered command: %s (aliases: %s)", name, getattr(handler, "aliases", []))
    
    def unregister(self, name: str) -> bool:
        if name in self._handlers:
            handler = self._handlers[name]
            for alias in getattr(handler, "aliases", []):
                self._handlers.pop(alias, None)
            del self._handlers[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Any]:
        return self._handlers.get(name.lower())
    
    def get_all(self) -> Dict[str, Any]:
        return dict(self._handlers)
    
    def get_help_text(self, admin: bool = False) -> str:
        lines = ["Komutlar:"]
        seen: set[int] = set()
        for handler in self._handlers.values():
            marker = id(handler)
            if marker in seen:
                continue
            seen.add(marker)
            if getattr(handler, "hidden", False):
                continue
            if getattr(handler, "admin_only", False) and not admin:
                continue
            aliases = " | ".join(getattr(handler, "aliases", [])) if getattr(handler, "aliases", []) else ""
            alias_part = f" ({aliases})" if aliases else ""
            lines.append(f"{handler.usage}{alias_part} - {handler.description}")
        return "\n".join(lines)
    
    def set_services(self, services: Dict[str, Any]) -> None:
        self._services = services
    
    def set_http_client(self, client) -> None:
        self._http_client = client
    
    def set_base_url(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        # Update all handlers
        for handler in self._handlers.values():
            if hasattr(handler, "_base_url"):
                handler._base_url = self._base_url
    
    def set_timeout(self, timeout: float) -> None:
        self._timeout = timeout
        for handler in self._handlers.values():
            if hasattr(handler, "_timeout"):
                handler._timeout = timeout
    
    async def handle(self, text: str, user_id: int = 0, username: str = "", 
                     chat_id: int = 0) -> Optional[str]:
        if not text.strip():
            return None
        
        parts = text.strip().split()
        if not parts:
            return None
        cmd = parts[0].lower()
        args = parts[1:]
        
        handler = self._handlers.get(cmd)
        if not handler:
            return None
        
        # Validate args
        is_valid, error = handler.validate_args(args) if hasattr(handler, "validate_args") else (True, None)
        if not is_valid:
            return f"Hata: {error}\nKullanım: {handler.usage}"
        
        try:
            context = CommandContext(
                args=args,
                raw_text=text,
                user_id=user_id,
                chat_id=chat_id,
                services=self._services.copy(),
            )
            
            result = await handler.execute(context)
            if result is None:
                return None
            
            if result.photo:
                return f"[PHOTO]{result.photo_caption or ''}"
            return result.text
            
        except Exception as exc:
            logger.exception("Command %s failed: %s", handler.name, exc)
            return f"Hata: {exc}"


# Global registry instance
_global_command_registry: Optional[CommandRegistry] = None
_registry_lock = asyncio.Lock()
_registry_sync_lock = threading.RLock()


def get_command_registry(base_url: str = "http://127.0.0.1:8080", 
                         timeout: float = 4.0) -> CommandRegistry:
    global _global_command_registry
    if _global_command_registry is None:
        with _registry_sync_lock:
            if _global_command_registry is None:
                _global_command_registry = CommandRegistry(base_url, timeout)
    return _global_command_registry


async def get_command_registry_async(base_url: str = "http://127.0.0.1:8080", 
                                      timeout: float = 4.0) -> CommandRegistry:
    global _global_command_registry
    async with _registry_sync_lock:
        if _global_command_registry is None:
            _global_command_registry = CommandRegistry(base_url, timeout)
    return _global_command_registry


def register_command(handler: Any) -> None:
    registry = get_command_registry()
    registry.register(handler)


async def register_command_async(handler: Any) -> None:
    registry = await get_command_registry_async()
    registry.register(handler)


def get_command_registry_instance() -> Optional[CommandRegistry]:
    return _global_command_registry


__all__ = [
    "CommandResult",
    "CommandContext",
    "CommandHandler",
    "CommandRegistry",
    "get_command_registry",
    "get_command_registry_async",
    "register_command",
    "register_command_async",
    "get_command_registry_instance",
    # Built-in handlers
    "HelpCommandHandler",
    "StatusCommandHandler",
    "SnapCommandHandler",
    "PanTiltCommandHandler",
    "PanCommandHandler",
    "TiltCommandHandler",
    "NeoFillCommandHandler",
    "NeoClearCommandHandler",
    "SayCommandHandler",
]