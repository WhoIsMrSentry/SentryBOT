from __future__ import annotations

import logging
from collections import deque
from typing import Deque, Iterable, List, Optional


class InMemoryLogHandler(logging.Handler):
    """Basit halka buffer log handler.

    - thread-safe: logging.Handler zaten lock içerir
    - formatlanmış stringleri saklar (emit sonrası)
    """

    def __init__(self, maxlen: int = 1000, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self.buffer: Deque[str] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = self.format(record)
        except Exception:  # pragma: no cover
            msg = record.getMessage()
        self.buffer.append(msg)

    def tail(self, n: int = 100) -> List[str]:
        if n <= 0:
            return []
        start = max(0, len(self.buffer) - n)
        return list(list(self.buffer)[start:])

    def iter(self) -> Iterable[str]:
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
