#!/usr/bin/env python3
"""Compare SentryBOT oled_faces motor catalog vs vendor/esp-bridge-mcp-robot upstream."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "esp-bridge-mcp-robot" / "src" / "modules" / "espbridge" / "eyes"


def _order_from_init(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "_ORDER" not in text:
        return []
    tail = text.split("_ORDER", 1)[1]
    return re.findall(r'"([a-z_]+)"', tail)


def _local_catalog() -> dict[str, set[str]]:
    sys.path.insert(0, str(ROOT))
    from modules.visual_output.oled_faces.services.catalog_registry import (  # noqa: WPS433
        MOTOR_ACTIVITIES,
        MOTOR_GESTURES,
        MOTOR_MOODS,
    )
    return {
        "moods": set(MOTOR_MOODS),
        "gestures": set(MOTOR_GESTURES),
        "activities": set(MOTOR_ACTIVITIES),
    }


def _upstream_catalog() -> dict[str, set[str]]:
    if not VENDOR.exists():
        print(f"Upstream not found: {VENDOR}")
        print("Run: git clone --depth 1 https://github.com/WhoIsMrSentry/esp-bridge-mcp-robot.git vendor/esp-bridge-mcp-robot")
        sys.exit(1)
    return {
        "moods": set(_order_from_init(VENDOR / "moods" / "__init__.py")),
        "gestures": set(_order_from_init(VENDOR / "gestures" / "__init__.py")),
        "activities": set(_order_from_init(VENDOR / "actions" / "__init__.py")),
    }


def _report(kind: str, local: set[str], upstream: set[str]) -> None:
    only_local = sorted(local - upstream)
    only_upstream = sorted(upstream - local)
    shared = sorted(local & upstream)
    print(f"\n## {kind}")
    print(f"  shared: {len(shared)}  |  sentrybot-only: {len(only_local)}  |  upstream-only: {len(only_upstream)}")
    if only_local:
        print(f"  + SentryBOT: {', '.join(only_local)}")
    if only_upstream:
        print(f"  + upstream (port candidate): {', '.join(only_upstream)}")


def main() -> None:
    local = _local_catalog()
    upstream = _upstream_catalog()
    print("Pip eyes catalog diff")
    print(f"Local:    modules/oled_faces/services/eyes/")
    print(f"Upstream: vendor/esp-bridge-mcp-robot/src/modules/espbridge/eyes/")
    for kind in ("moods", "gestures", "activities"):
        _report(kind, local[kind], upstream[kind])
    print("\nDone. Robot-specific extras are intentional; upstream-only items are port candidates.")


if __name__ == "__main__":
    main()
