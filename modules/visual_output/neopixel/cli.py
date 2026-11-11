from __future__ import annotations

import sys

from modules.visual_output.neopixel.config_loader import load_config
from modules.visual_output.neopixel.services.driver import NeoDriverConfig
from modules.visual_output.neopixel.services.runner import NeoRunner


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = load_config()
    hw = cfg.get("hardware", {}) if isinstance(cfg.get("hardware"), dict) else {}
    drv_cfg = NeoDriverConfig(
        device=str(hw.get("device", "/dev/spidev0.0")),
        num_leds=int(hw.get("num_leds", 23)),
        speed_khz=int(hw.get("speed_khz", 800)),
        ws2812_spi_khz=int(hw.get("ws2812_spi_khz", 2400)),
        backend=str(hw.get("backend", "auto")),
        order=str(hw.get("order", "GRB")),
        max_brightness=float(hw.get("max_brightness", 0.7)),
        max_current_ma=int(hw.get("max_current_ma", 900)),
    )
    runner = NeoRunner(drv_cfg, segments=hw.get("segments", []))
    cmd = argv[0].lower() if argv else "demo"
    keep_lit = False
    try:
        if cmd == "rainbow":
            runner.rainbow()
            runner._wait_for_animations(timeout=5.0)
        elif cmd == "chase":
            runner.theater_chase()
            runner._wait_for_animations(timeout=5.0)
        elif cmd == "clear":
            runner.clear()
        elif cmd == "fill":
            r = int(argv[1]) if len(argv) > 1 else 255
            g = int(argv[2]) if len(argv) > 2 else 255
            b = int(argv[3]) if len(argv) > 3 else 255
            runner.fill(r, g, b)
            keep_lit = True
        else:
            runner.fill(255, 0, 0)
            runner.fill(0, 255, 0)
            runner.fill(0, 0, 255)
            runner.fill(255, 255, 255)
    finally:
        runner.stop(clear=not keep_lit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
