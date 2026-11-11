from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("piservo.driver")


@dataclass
class ServoConfig:
    gpio: int
    min_us: int = 500
    max_us: int = 2500
    min_deg: float = 0.0
    max_deg: float = 180.0
    center_deg: float = 90.0
    # Optional Arduino override when ear servo is routed over Arduino Mega
    arduino_index: Optional[int] = None


class _PigpioWrapper:
    backend_name = "pigpio"

    def __init__(self) -> None:
        import pigpio  # type: ignore

        self._pi = pigpio.pi()
        if not getattr(self._pi, "connected", True):
            raise RuntimeError("pigpio daemon not connected")
        self._active_gpios: Set[int] = set()
        self.last_error: Optional[str] = None
        self.closed = False

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        if self.closed:
            return
        try:
            self._pi.set_servo_pulsewidth(gpio, int(pulsewidth))
            if int(pulsewidth) == 0:
                self._active_gpios.discard(gpio)
            else:
                self._active_gpios.add(gpio)
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("pigpio set_servo_pulsewidth(%s) failed: %s", gpio, exc)

    def detach(self, gpio: int) -> None:
        self.set_servo_pulsewidth(gpio, 0)

    def close(self) -> None:
        if self.closed:
            return
        for gpio in list(self._active_gpios):
            self.set_servo_pulsewidth(gpio, 0)
        self.closed = True
        try:
            self._pi.stop()
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("pigpio stop failed: %s", exc)


class _LgpioWrapper:
    """Shared RPi 5 / kernel GPIO driver using lgpio."""

    backend_name = "lgpio"

    def __init__(self) -> None:
        import lgpio  # type: ignore

        self._lgpio = lgpio
        self._chip: Optional[int] = None
        self._active_gpios: Set[int] = set()
        self.last_error: Optional[str] = None
        self.closed = False
        for chip_num in (4, 0, 1):
            try:
                self._chip = lgpio.gpiochip_open(chip_num)
                break
            except Exception as exc:
                self.last_error = str(exc)
        if self._chip is None:
            raise RuntimeError("Cannot open gpiochip with lgpio")

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        if self.closed or self._chip is None:
            return
        try:
            pw = int(pulsewidth)
            duty_cycle = 0.0 if pw <= 0 else (pw / 20000.0) * 100.0
            self._lgpio.tx_pwm(self._chip, gpio, 50, duty_cycle)
            if pw <= 0:
                self._active_gpios.discard(gpio)
            else:
                self._active_gpios.add(gpio)
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("lgpio tx_pwm(gpio=%s) failed: %s", gpio, exc)

    def detach(self, gpio: int) -> None:
        self.set_servo_pulsewidth(gpio, 0)

    def close(self) -> None:
        if self.closed:
            return
        for gpio in list(self._active_gpios):
            self.set_servo_pulsewidth(gpio, 0)
        self.closed = True
        if self._chip is not None:
            try:
                self._lgpio.gpiochip_close(self._chip)
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("lgpio gpiochip_close failed: %s", exc)
            self._chip = None


class _SimGPIO:
    backend_name = "sim"

    def __init__(self) -> None:
        self.pulses: Dict[int, int] = {}
        self.last_error: Optional[str] = None
        self.closed = False

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        if self.closed:
            return
        self.pulses[gpio] = int(pulsewidth)

    def detach(self, gpio: int) -> None:
        self.set_servo_pulsewidth(gpio, 0)

    def close(self) -> None:
        if self.closed:
            return
        for gpio in list(self.pulses):
            self.pulses[gpio] = 0
        self.closed = True


class _ArduinoWrapper:
    backend_name = "arduino"

    def __init__(self, index: int, cfg: Optional[ServoConfig] = None, driver: Optional[Any] = None):
        if driver is not None:
            self._drv = driver
            self._owns_driver = False
        else:
            try:
                from modules.arduino_serial.services.driver import ArduinoDriver  # type: ignore
            except ImportError as exc:
                raise RuntimeError("ArduinoDriver not available") from exc
            self._drv = ArduinoDriver()
            self._owns_driver = True
            try:
                self._drv.start()
            except Exception as exc:
                logger.warning("ArduinoDriver start failed for ear servo %s: %s", index, exc)
        self._index = index
        self._cfg = cfg
        self.last_error: Optional[str] = None
        self.closed = False

    def _us_to_deg(self, pulsewidth: int) -> float:
        cfg = self._cfg or ServoConfig(gpio=0)
        span_us = max(1, cfg.max_us - cfg.min_us)
        span_deg = cfg.max_deg - cfg.min_deg
        frac = (float(pulsewidth) - cfg.min_us) / float(span_us)
        deg = cfg.min_deg + frac * span_deg
        return max(cfg.min_deg, min(cfg.max_deg, deg))

    def set_servo_pulsewidth(self, gpio: int, pulsewidth: int) -> None:
        if self.closed:
            return
        pw = int(pulsewidth)
        if pw <= 0:
            # 0 means idle PWM detach on local Pi GPIO; do not jump Arduino servos to min_deg.
            return
        deg = self._us_to_deg(pw)
        try:
            self._drv.svc.set_servo(self._index, deg, wait_ack=False)
        except TypeError:
            try:
                self._drv.svc.set_servo(self._index, deg)
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("Arduino set_servo(idx=%s) failed: %s", self._index, exc)
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Arduino set_servo(idx=%s) failed: %s", self._index, exc)

    def detach(self, gpio: int) -> None:
        self.set_servo_pulsewidth(gpio, 0)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._owns_driver and hasattr(self._drv, "stop"):
            try:
                self._drv.stop()
            except Exception as exc:
                logger.warning("ArduinoDriver stop failed: %s", exc)


def create_pi_gpio_backend() -> Any:
    """Create one shared Pi GPIO PWM backend (pigpio -> lgpio -> simulation fallback)."""
    for cls in (_PigpioWrapper, _LgpioWrapper):
        try:
            return cls()
        except Exception as exc:
            logger.debug("%s unavailable (%s); trying next backend", cls.backend_name, exc)
    logger.warning("Neither pigpio nor lgpio is available; falling back to _SimGPIO")
    return _SimGPIO()


class Servo:
    def __init__(self, cfg: ServoConfig, backend: Optional[Any] = None):
        self.cfg = cfg
        self._owns_backend = False
        self.pwm_active = False

        if backend is not None:
            self._io = backend
        elif self.cfg.arduino_index is not None:
            self._owns_backend = True
            try:
                self._io = _ArduinoWrapper(int(self.cfg.arduino_index), cfg=self.cfg)
            except Exception as exc:
                logger.warning("Arduino ear backend init failed (%s); falling back to Pi GPIO", exc)
                self._io = create_pi_gpio_backend()
        else:
            self._owns_backend = True
            self._io = create_pi_gpio_backend()

    @property
    def backend_name(self) -> str:
        return str(getattr(self._io, "backend_name", self._io.__class__.__name__))

    @property
    def last_error(self) -> Optional[str]:
        return getattr(self._io, "last_error", None)

    def angle_to_us(self, angle: float) -> int:
        angle = max(self.cfg.min_deg, min(self.cfg.max_deg, float(angle)))
        span_deg = self.cfg.max_deg - self.cfg.min_deg
        span_us = self.cfg.max_us - self.cfg.min_us
        frac = (angle - self.cfg.min_deg) / span_deg if span_deg else 0.0
        return int(self.cfg.min_us + frac * span_us)

    def set_angle(self, angle: float) -> None:
        pw = self.angle_to_us(angle)
        self._io.set_servo_pulsewidth(self.cfg.gpio, pw)
        self.pwm_active = True

    def detach(self) -> None:
        if hasattr(self._io, "detach"):
            self._io.detach(self.cfg.gpio)
        else:
            self._io.set_servo_pulsewidth(self.cfg.gpio, 0)
        self.pwm_active = False

    def close(self) -> None:
        self.detach()
        if self._owns_backend and hasattr(self._io, "close"):
            self._io.close()
