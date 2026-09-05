from __future__ import annotations

import logging
from collections import deque
from typing import Deque, Iterable, List, Optional


class InMemoryLogHandler(logging.Handler):
    """Basit halka buffer log handler.

    Backwards-compatible davranış korundu: `tail()` eski gibi formatlanmış string listesi döner.
    Ek olarak yapılandırılmış kayıtlar için `tail_struct()` ve `iter_struct()` eklendi.

    - thread-safe: logging.Handler zaten lock içerir
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
        self.buffer.append(entry)

    def tail(self, n: int = 100) -> List[str]:
        """Geriye dönük en son n formatlanmış string'i döner (geri uyumluluk)."""
        if n <= 0:
            return []
        start = max(0, len(self.buffer) - n)
        return [e["formatted"] for e in list(self.buffer)[start:]]

    def iter(self) -> Iterable[str]:
        """Eski iter benzeri, formatlanmış string'ler döner."""
        return (e["formatted"] for e in self.buffer)

    # Yeni API: yapılandırılmış kayıtlara erişim
    def tail_struct(self, n: int = 100) -> List[dict]:
        if n <= 0:
            return []
        start = max(0, len(self.buffer) - n)
        return list(self.buffer)[start:]

    def iter_struct(self) -> Iterable[dict]:
        return iter(self.buffer)


def build_formatter(json_format: bool) -> logging.Formatter:
    if json_format:
        # Minimal JSON without extra deps
        fmt = (
            '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s"'
            ',"msg":"%(message)s","module":"%(module)s","line":%(lineno)d}'
        )
        datefmt = "%Y-%m-%dT%H:%M:%S"
        return logging.Formatter(fmt=fmt, datefmt=datefmt)
    # Human friendly
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%H:%M:%S"
    return logging.Formatter(fmt=fmt, datefmt=datefmt)


class WarningOnlyFilter(logging.Filter):
    """Allows WARNING records while keeping ERROR and CRITICAL in error logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return logging.WARNING <= record.levelno < logging.ERROR