from __future__ import annotations

import logging
import logging.config
import os
import warnings
from typing import Any, Dict, Optional

from .config_loader import load_config
from .services.handlers import InMemoryLogHandler, WarningOnlyFilter, build_formatter

_MEMORY_HANDLER: Optional[InMemoryLogHandler] = None
_ROUTER = None  # lazy import for FastAPI


class EndpointFilter(logging.Filter):
    """Specific paths like healthz or polling should not flood the console."""

    def __init__(self, suppressed_paths: list[str]):
        super().__init__()
        self.suppressed_paths = suppressed_paths

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access logs have the path in the message
        msg = record.getMessage()
        for path in self.suppressed_paths:
            if path in msg:
                return False
        return True


def _ensure_log_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _console_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    console_cfg = cfg.get("console") or {}
    mode = str(os.getenv("SENTRYBOT_CONSOLE_MODE", console_cfg.get("mode", "dashboard"))).lower()
    level = cfg.get("console_level", "INFO")
    if mode in {"off", "none", "silent", "tui"}:
        return {"class": "logging.NullHandler", "level": level}
    if mode == "dashboard":
        return {
            "()": "modules.runtime_console.dashboard.RuntimeConsoleLogHandler",
            "level": level,
            "mode": mode,
            "colors": bool(console_cfg.get("colors", True)),
            "show_background_requests": bool(console_cfg.get("show_background_requests", False)),
            "aggregate_repeated_messages": bool(console_cfg.get("aggregate_repeated_messages", True)),
            "repeat_summary_interval_s": int(console_cfg.get("repeat_summary_interval_s", 30)),
            "event_history": int(console_cfg.get("event_history", 8)),
            "max_message_width": int(console_cfg.get("max_message_width", 92)),
            "border": str(console_cfg.get("border", "rounded")),
        }
    return {
        "class": "logging.StreamHandler",
        "level": level,
        "stream": "ext://sys.stdout",
    }


def init_logging(overrides: Optional[Dict[str, Any]] = None) -> None:
    """Kök logger'ı merkezi olarak yapılandırır.

    - Tüm modüllerin logları toplanır (disable_existing_loggers=False)
    - Console ve dosya handler isteğe bağlı
    - Bellek içi halka buffer handler
    - Warnings capture
    """
    global _MEMORY_HANDLER

    # Zaten kuruluysa tekrar yapılandırma
    if _MEMORY_HANDLER is not None and logging.getLogger().handlers:
        return

    cfg = load_config(overrides=overrides)

    handlers: Dict[str, Dict[str, Any]] = {}
    root_handlers = []

    # Memory handler
    memory_name = "in_memory"
    handlers[memory_name] = {
        "()": InMemoryLogHandler,
        "maxlen": int(cfg.get("buffer_size", 1000)),
        "level": "DEBUG",
    }
    root_handlers.append(memory_name)

    # Console handler
    if cfg.get("enable_console", True):
        handlers["console"] = _console_config(cfg)
        root_handlers.append("console")

    # File handler with rotation. Keep this detailed even when console hides noise.
    split_files = cfg.get("separate_files", {})
    split_files = split_files if isinstance(split_files, dict) else {}
    if bool(split_files.get("enabled", False)):
        max_bytes = int(cfg.get("rotate_bytes", 2 * 1024 * 1024))
        backups = int(cfg.get("backup_count", 5))
        warning_path = str(split_files.get("warnings_path", "logs/warnings.log"))
        error_path = str(split_files.get("errors_path", "logs/errors.log"))
        tui_path = str(split_files.get("tui_path", "logs/tui.log"))
        for path in (warning_path, error_path, tui_path):
            _ensure_log_dir(path)
        handlers["warnings_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "WARNING",
            "filters": ["warning_only"],
            "filename": warning_path,
            "maxBytes": max_bytes,
            "backupCount": backups,
            "encoding": "utf-8",
        }
        handlers["errors_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "filename": error_path,
            "maxBytes": max_bytes,
            "backupCount": backups,
            "encoding": "utf-8",
        }
        handlers["tui_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "filename": tui_path,
            "maxBytes": max_bytes,
            "backupCount": backups,
            "encoding": "utf-8",
        }
        root_handlers.extend(["warnings_file", "errors_file"])
        handlers["tui_file"]["level"] = "DEBUG"
    elif cfg.get("enable_file", True):
        path = str(cfg.get("file_path", "logs/sentry.log"))
        _ensure_log_dir(path)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "filename": path,
            "maxBytes": int(cfg.get("rotate_bytes", 2 * 1024 * 1024)),
            "backupCount": int(cfg.get("backup_count", 5)),
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    # Formatters
    json_format = bool(cfg.get("json_format", False))
    formatter = build_formatter(json_format)

    # dictConfig yapılandırması
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": lambda: formatter,
                }
            },
            "filters": {"warning_only": {"()": "modules.logwrapper.services.handlers.WarningOnlyFilter"}},
            "handlers": {
                name: {
                    **opts,
                    "formatter": "default",
                }
                for name, opts in handlers.items()
            },
            "loggers": {
                "runtime_console": {"level": "DEBUG", "handlers": ["tui_file"], "propagate": True},
                "uvicorn.access": {
                    "level": "WARNING",
                    "handlers": root_handlers,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": "INFO",
                    "handlers": root_handlers,
                    "propagate": False,
                },
            },
            "root": {
                "level": "DEBUG",
                "handlers": root_handlers,
            },
        }
    )

    # Warnings -> logging
    if cfg.get("capture_warnings", True):
        logging.captureWarnings(True)
        warnings.simplefilter("default")
        # Optional: tone down known 3rd-party deprecations
        try:
            warnings.filterwarnings(
                "ignore",
                message=r".*pkg_resources\.declare_namespace.*",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r".*pkg_resources is deprecated as an API.*",
                category=Warning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r".*UnsupportedFieldAttributeWarning.*validate_default.*",
                category=Warning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r".*validate_default.*has no effect.*",
                category=UserWarning,
                module=r"pydantic\._internal\._generate_schema",
            )
            warnings.filterwarnings(
                "ignore",
                message=r".*websockets\.legacy is deprecated.*",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r".*WebSocketServerProtocol is deprecated.*",
                category=DeprecationWarning,
            )
        except Exception:
            pass

    # Formatter instance'ını memory handler'a bağlamak için referans bulalım
    logger = logging.getLogger()
    for h in logger.handlers:
        if isinstance(h, InMemoryLogHandler):
            h.setFormatter(formatter)
            _MEMORY_HANDLER = h
            break

    # Module bazlı level override
    for name, level in (cfg.get("module_levels") or {}).items():
        try:
            logging.getLogger(name).setLevel(getattr(logging, str(level).upper()))
        except Exception:
            logging.getLogger(name).setLevel(level)

    # Apply endpoint filtering to noisy console logs only. File logging keeps full detail.
    suppressed = list((cfg.get("console") or {}).get("hidden_paths") or [])
    if not suppressed:
        suppressed = [
            "/camera/healthz",
            "/vlm/context/latest",
            "/vlm/results/latest",
            "/telemetry/metrics",
            "/speech/direction",
            "/speech/last",
            "/arduino/healthz",
            "/state/set/emotions",
            "/interactions/event",
            "/interactions/effect",
            "/neopixel/animate",
            "/oled_faces/manual",
        ]
    ef = EndpointFilter(suppressed)

    logging.getLogger("uvicorn.access").addFilter(ef)
    for handler in logging.getLogger().handlers:
        handler_name = handler.__class__.__name__
        if handler_name in {"StreamHandler", "RuntimeConsoleLogHandler"}:
            handler.addFilter(ef)


def get_memory_handler() -> Optional[InMemoryLogHandler]:
    return _MEMORY_HANDLER


def get_router():  # lazy import to avoid FastAPI dep when unused
    global _ROUTER
    if _ROUTER is not None:
        return _ROUTER
    try:
        from .api.router import router  # type: ignore
    except Exception:  # FastAPI yoksa API opsiyonel
        return None
    _ROUTER = router
    return _ROUTER


if __name__ == "__main__":
    # Servis gibi çalıştırıldığında basit demo
    init_logging()
    log = logging.getLogger("logwrapper.demo")
    log.info("Logwrapper service started")
    log.warning("This is a warning")
    log.error("This is an error")
