from __future__ import annotations

from typing import Any


class _SegmentView:
    """Adapter that exposes a driver sub-range as if it were a full strip."""

    def __init__(self, driver: Any, start: int, end: int) -> None:
        self._driver = driver
        self._start = start
        self._end = end
        self.num_leds = max(0, end - start)

    def set(self, idx: int, r: int, g: int, b: int) -> None:
        if 0 <= idx < self.num_leds:
            self._driver.set(self._start + idx, r, g, b)

    def show(self) -> None:
        self._driver.show()

    def clear(self) -> None:
        for i in range(self._start, self._end):
            self._driver.set(i, 0, 0, 0)
        self._driver.show()

    def fill(self, r: int, g: int, b: int) -> None:
        for i in range(self._start, self._end):
            self._driver.set(i, r, g, b)
        self._driver.show()


class _AnimationCancelled(RuntimeError):
    pass


class _AnimationDriver:
    """Buffer animation frames and reject writes from cancelled animations."""

    def __init__(self, runner: Any, generation: int) -> None:
        self._runner = runner
        self._generation = generation
        self._pending: dict[int, tuple[int, int, int]] = {}
        self.num_leds = runner.driver.num_leds

    def _check(self) -> None:
        if not self._runner._animation_is_current(self._generation):
            raise _AnimationCancelled()

    def set(self, idx: int, r: int, g: int, b: int) -> None:
        self._check()
        if 0 <= idx < self.num_leds:
            self._pending[idx] = (r, g, b)

    def show(self) -> None:
        self._check()
        with self._runner._frame_lock:
            self._check()
            for idx, color in self._pending.items():
                self._runner.driver.set(idx, *color)
            self._runner.driver.show()
        self._pending.clear()

    def clear(self) -> None:
        self._check()
        self._pending.clear()
        with self._runner._frame_lock:
            self._check()
            self._runner.driver.clear()

    def fill(self, r: int, g: int, b: int) -> None:
        self._check()
        self._pending.clear()
        with self._runner._frame_lock:
            self._check()
            self._runner.driver.fill(r, g, b)

    def animate(
        self,
        name: str,
        r: int = 255,
        g: int = 255,
        b: int = 255,
        iterations: int = 0,
        speed_ms: int = 50,
    ) -> bool:
        self._check()
        return False
