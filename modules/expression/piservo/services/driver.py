from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class ServoConfig:
    gpio: int
    min_us: int = 500
    max_us: int = 2500
    min_deg: float = 0.0
    max_deg: float = 180.0
    center_deg: float = 90.0
    # If set, use Arduino backend and this is the servo index on Arduino's controller
    arduino_index: Optional[int] = None


class _PigpioWrapper:
    def __init__(self) -> None:
        import pigpio  # type: ignore
        self._pi = pigpio.pi()

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        self._pi.set_servo_pulsewidth(gpio, pulsewidth)


class _SimGPIO:
    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        # Simulation: no-op
        pass


class _ArduinoWrapper:
    def __init__(self, index: int):
        # Lazy import to avoid hard dependency
        try:
            from modules.arduino_serial.services.driver import ArduinoDriver  # type: ignore
        except Exception:
            try:
                from ..arduino_serial.services.driver import ArduinoDriver  # type: ignore
            except Exception:
                ArduinoDriver = None  # type: ignore
        if ArduinoDriver is None:
            raise RuntimeError("ArduinoDriver not available")
        self._drv = ArduinoDriver()
        try:
            self._drv.start()
        except Exception:
            pass
        self._index = index

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        # Convert pulsewidth back to degrees using caller mapping isn't available here;
        # Arduino driver exposes `set_servo(index, deg)`. We'll compute deg approximately
        # using typical 500-2500 us mapping if possible.
        try:
            # approximate mapping
            us = int(pulsewidth)
            # map 500..2500 -> 0..180
            deg = max(0.0, min(180.0, (us - 500) * 180.0 / 2000.0))
            self._drv.svc.set_servo(self._index, deg)
        except Exception:
            pass


class Servo:
    def __init__(self, cfg: ServoConfig):
        self.cfg = cfg
        # Prefer Arduino backend when available. Use explicit `arduino_index` if provided,
        # otherwise, if ArduinoDriver exists, try using the `gpio` as an index (common when
        # using PCA9685 channel numbers). Fallback to pigpio, then sim.
        ArduinoDriver = None
        try:
            from modules.arduino_serial.services.driver import ArduinoDriver  # type: ignore
        except Exception:
            try:
                from ..arduino_serial.services.driver import ArduinoDriver  # type: ignore
            except Exception:
                ArduinoDriver = None  # type: ignore

        if ArduinoDriver is not None:
            # Decide an index: prefer explicit config arduino_index; otherwise try gpio if reasonable
            idx = None
            if self.cfg.arduino_index is not None:
                idx = int(self.cfg.arduino_index)
            else:
                # If gpio looks like a small PCA9685 channel (0..15) use it
                try:
                    if 0 <= int(self.cfg.gpio) <= 15:
                        idx = int(self.cfg.gpio)
                except Exception:
                    idx = None

            if idx is not None:
                try:
                    self._io = _ArduinoWrapper(idx)
                except Exception:
                    self._io = None
            else:
                self._io = None
        else:
            self._io = None

        if self._io is None:
            try:
                self._io = _PigpioWrapper()
            except Exception:
                self._io = _SimGPIO()

    def angle_to_us(self, angle: float) -> int:
        angle = max(self.cfg.min_deg, min(self.cfg.max_deg, angle))
        span_deg = self.cfg.max_deg - self.cfg.min_deg
        span_us = self.cfg.max_us - self.cfg.min_us
        frac = (angle - self.cfg.min_deg) / span_deg if span_deg else 0
        return int(self.cfg.min_us + frac * span_us)

    def set_angle(self, angle: float) -> None:
        pw = self.angle_to_us(angle)
        self._io.set_servo_pulsewidth(self.cfg.gpio, pw)
