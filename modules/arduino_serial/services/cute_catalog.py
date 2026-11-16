from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("arduino_serial.cute_catalog")

_MAPPING_PATH = Path(__file__).resolve().parent.parent / "config" / "cute_mapping.json"


def load_cute_sound_catalog(path: Path = _MAPPING_PATH) -> Dict[str, Dict[str, Any]]:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning("failed loading cute catalog from %s: %s", path, exc)
    return {}


CUTE_SOUND_CATALOG: Dict[str, Dict[str, Any]] = load_cute_sound_catalog()

EMOTION_TO_CUTE: Dict[str, str] = {
    "happy": "happy",
    "super_happy": "super_happy",
    "sad": "sad",
    "surprise": "surprise",
    "confused": "confused",
    "sleeping": "sleeping",
    "connected": "connection",
    "disconnected": "disconnection",
}
