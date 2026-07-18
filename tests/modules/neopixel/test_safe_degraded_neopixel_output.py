from __future__ import annotations

from modules.interactions.services.adapters.neopixel_client import (
    NEOPIXEL_SAFE_DEGRADED_CLIENT_CONTRACT,
    NOOP_NEOPIXEL_CLIENT_ROLE,
    NoOpNeoClient,
)
from modules.neopixel.services.driver import (
    NEOPIXEL_SAFE_DEGRADED_DRIVER_CONTRACT,
    NEOPIXEL_SIMULATOR_BACKEND_ROLE,
    _SimStrip,
)


def test_noop_neopixel_client_is_explicit_safe_degraded_adapter():
    assert NEOPIXEL_SAFE_DEGRADED_CLIENT_CONTRACT is True
    assert NOOP_NEOPIXEL_CLIENT_ROLE == "safe_degraded_output_adapter"
    client = NoOpNeoClient()
    assert client.clear() is None
    assert client.fill(1, 2, 3) is None
    assert client.animate("idle") is None
    assert client.set_base("calm") is None
    assert client.play_effect("blink", duration_ms=0) is None
    assert client.companion_mode("idle") is None
    assert client.companion_vu(0.2) is None


def test_sim_strip_is_memory_only_and_never_claims_hardware_animation():
    assert NEOPIXEL_SAFE_DEGRADED_DRIVER_CONTRACT is True
    assert NEOPIXEL_SIMULATOR_BACKEND_ROLE == "safe_degraded_memory_only_led_buffer"
    strip = _SimStrip(3)
    strip.set_led_color(1, 10, 20, 30)
    assert strip.buf[1] == (10, 20, 30)
    assert strip.animate("rainbow", 1, 2, 3, 1, 10) is False
    strip.clear_strip()
    assert strip.buf == [(0, 0, 0), (0, 0, 0), (0, 0, 0)]
