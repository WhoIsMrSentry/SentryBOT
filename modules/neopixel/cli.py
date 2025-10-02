from __future__ import annotations
import sys

from modules.neopixel.services.driver import NeoDriverConfig
from modules.neopixel.services.runner import NeoRunner


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    runner = NeoRunner(NeoDriverConfig())
    try:
        if argv and argv[0] == "rainbow":
            runner.rainbow()
        elif argv and argv[0] == "chase":
            runner.theater_chase()
        elif argv and argv[0] == "fill":
            r = int(argv[1]) if len(argv) > 1 else 255
            g = int(argv[2]) if len(argv) > 2 else 255
            b = int(argv[3]) if len(argv) > 3 else 255
            runner.fill(r, g, b)
        else:
            # demo sequence
            runner.fill(255, 0, 0)
            runner.fill(0, 255, 0)
            runner.fill(0, 0, 255)
            runner.fill(255, 255, 255)
    finally:
        runner.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
