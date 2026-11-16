from __future__ import annotations

import json
import logging
from collections import deque
from typing import Deque, Iterable, List


class InMemoryLogHandler(logging.Handler):
    """Basit halka buffer log handler.

    Backwards-compatible davranış korundu: `tail()` eski gibi formatlanmış string listesi döner.
    Ek olarak yapılandırılmış kayıtlar için `tail_struct()` ve `iter_struct()` eklendi.

    - thread-safe: tüm okuma/yazma işlemleri `self.lock` ile korunur
    - formatlanmış stringleri ve parçalara ayrılmış meta veriyi saklar (emit sonrası)
    """

    def __init__(self, maxlen: int = 1000, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        # iç buffer dict'ler tutar: {formatted, name, levelname, message, asctime}
        self.buffer: Deque[dict] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            formatted = self.format(record)
        except Exception:  # pragma: no cover
            formatted = record.getMessage()
        entry = {
            "formatted": formatted,
            "name": getattr(record, "name", ""),
            "level": getattr(record, "levelname", ""),
            "message": record.getMessage(),
            "asctime": getattr(record, "asctime", ""),
        }
        with self.lock:
            self.buffer.append(entry)

    def tail(self, n: int = 100) -> List[str]:
        """Geriye dönük en son n formatlanmış string'i döner (geri uyumluluk)."""
        if n <= 0:
            return []
        with self.lock:
            start = max(0, len(self.buffer) - n)
            return [e["formatted"] for e in list(self.buffer)[start:]]

    def iter(self) -> Iterable[str]:
        """Anlık kopya üzerinden formatlanmış string'ler döner."""
        with self.lock:
            items = [e["formatted"] for e in self.buffer]
        return iter(items)

    # Yeni API: yapılandırılmış kayıtlara erişim
    def tail_struct(self, n: int = 100) -> List[dict]:
        if n <= 0:
            return []
        with self.lock:
            start = max(0, len(self.buffer) - n)
            return list(self.buffer)[start:]

    def iter_struct(self) -> Iterable[dict]:
        with self.lock:
            items = list(self.buffer)
        return iter(items)


class _JsonLogFormatter(logging.Formatter):
    """Structured single-line JSON log formatter using json.dumps for safe escaping."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def build_formatter(json_format: bool) -> logging.Formatter:
    if json_format:
        return _JsonLogFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    # Human friendly
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%H:%M:%S"
    return logging.Formatter(fmt=fmt, datefmt=datefmt)


class WarningOnlyFilter(logging.Filter):
    """Allows WARNING records while keeping ERROR and CRITICAL in error logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return logging.WARNING <= record.levelno < logging.ERROR