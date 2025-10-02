from __future__ import annotations

import logging
import logging.config
import os
import warnings
from typing import Any, Dict, Optional

from .config_loader import load_config
from .services.handlers import InMemoryLogHandler, build_formatter

_MEMORY_HANDLER: Optional[InMemoryLogHandler] = None
_ROUTER = None  # lazy import for FastAPI


def _ensure_log_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


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
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "level": cfg.get("console_level", "INFO"),
            "stream": "ext://sys.stdout",
        }
        root_handlers.append("console")

    # File handler with rotation
    if cfg.get("enable_file", True):
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
            "handlers": {
                name: {
                    **opts,
                    "formatter": "default",
                }
                for name, opts in handlers.items()
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
                category=DeprecationWarning,
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
