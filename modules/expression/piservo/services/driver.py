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
        if not getattr(self._pi, "connected", True):
            raise RuntimeError("pigpio daemon not connected")

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        self._pi.set_servo_pulsewidth(gpio, pulsewidth)


class _LgpioWrapper:
    """RPi5 / Kernel GPIO driver using lgpio."""
    def __init__(self) -> None:
        import lgpio  # type: ignore
        self._lgpio = lgpio
        self._chip = None
        for chip_num in (4, 0, 1):
            try:
                self._chip = lgpio.gpiochip_open(chip_num)
                break
            except Exception:
                continue
        if self._chip is None:
            raise RuntimeError("Cannot open gpiochip with lgpio")

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        try:
            duty_cycle = (pulsewidth / 20000.0) * 100.0
            self._lgpio.tx_pwm(self._chip, gpio, 50, duty_cycle)
        except Exception:
            pass


class _SimGPIO:
    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        # Simulation: no-op
        pass


class _ArduinoWrapper:
    def __init__(self, index: int):
        try:
            from modules.arduino_serial.services.driver import ArduinoDriver  # type: ignore
        except Exception:
            ArduinoDriver = None
        if ArduinoDriver is None:
            raise RuntimeError("ArduinoDriver not available")
        self._drv = ArduinoDriver()
        try:
            self._drv.start()
        except Exception:
            pass
        self._index = index

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        try:
            us = int(pulsewidth)
            deg = max(0.0, min(180.0, (us - 500) * 180.0 / 2000.0))
            self._drv.svc.set_servo(self._index, deg)
        except Exception:
            pass


class Servo:
    def __init__(self, cfg: ServoConfig):
        self.cfg = cfg
        self._io = None

        # Kulak servoları doğrudan Raspberry Pi GPIO'suna aittir.
        # Yalnızca konfigürasyonda açıkça arduino_index belirtilmişse Arduino denenir.
        if self.cfg.arduino_index is not None:
            try:
                self._io = _ArduinoWrapper(int(self.cfg.arduino_index))
            except Exception:
                self._io = None

        # Pi GPIO Donanım Sürücüleri: pigpio -> lgpio (RPi 5) -> Simulatör
        if self._io is None:
            try:
                self._io = _PigpioWrapper()
            except Exception:
                try:
                    self._io = _LgpioWrapper()
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
