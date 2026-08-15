from __future__ import annotations

import logging
from pathlib import Path

from modules.logwrapper import xLogService as service


def test_separate_warning_error_and_tui_files(tmp_path: Path, monkeypatch):
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_memory = service._MEMORY_HANDLER
    root.handlers.clear()
    service._MEMORY_HANDLER = None
    monkeypatch.chdir(tmp_path)
    try:
        service.init_logging(
            {
                "enable_console": False,
                "capture_warnings": False,
                "separate_files": {
                    "enabled": True,
                    "warnings_path": "logs/warnings.log",
                    "errors_path": "logs/errors.log",
                    "tui_path": "logs/tui.log",
                },
            }
        )
        logging.getLogger("runtime_console.test").info("tui-only-message")
        logging.getLogger("robot.test").warning("warning-message")
        logging.getLogger("robot.test").error("error-message")
        for handler in logging.getLogger().handlers:
            handler.flush()
        for handler in logging.getLogger("runtime_console").handlers:
            handler.flush()

        warning_log = (tmp_path / "logs" / "warnings.log").read_text(encoding="utf-8")
        error_log = (tmp_path / "logs" / "errors.log").read_text(encoding="utf-8")
        tui_log = (tmp_path / "logs" / "tui.log").read_text(encoding="utf-8")
        assert "warning-message" in warning_log
        assert "error-message" not in warning_log
        assert "warning-message" not in error_log
        assert "error-message" in error_log
        assert "tui-only-message" in tui_log
    finally:
        for handler in logging.getLogger().handlers:
            handler.close()
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        service._MEMORY_HANDLER = original_memory