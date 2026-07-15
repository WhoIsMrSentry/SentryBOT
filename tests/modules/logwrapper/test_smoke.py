from __future__ import annotations

import logging

from modules.logwrapper import init_logging, get_memory_handler


def test_smoke_memory_handler():
    init_logging({"enable_file": False})  # file IO'yu kapat
    log = logging.getLogger("modules.logwrapper.test")
    log.debug("dbg")
    log.info("info")
    handler = get_memory_handler()
    assert handler is not None
    items = handler.tail(5)
    assert any("info" in i or "INFO" in i for i in items)
