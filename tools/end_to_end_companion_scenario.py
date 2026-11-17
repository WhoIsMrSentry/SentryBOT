from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.companion_e2e_robot_test import call


def main() -> int:
    parser = argparse.ArgumentParser(description="Run single-shot companion E2E scenario via Gateway.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--mode", default="safe")
    parser.add_argument("--allow-motion", action="store_true")
    args = parser.parse_args()

    result = call(
        "POST",
        args.base_url,
        "/autonomy/scenario/e2e",
        {"mode": args.mode, "allow_motion": bool(args.allow_motion)},
        timeout=15.0,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
