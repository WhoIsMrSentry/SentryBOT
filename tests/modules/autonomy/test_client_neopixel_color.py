"""Tests for NeoPixel color forwarding in autonomy client."""
from __future__ import annotations

from unittest.mock import patch

from modules.autonomy.services.client import ServiceClient


def test_parse_rgb_from_list():
    assert ServiceClient._parse_rgb([220, 40, 0]) == (220, 40, 0)


def test_parse_rgb_from_hex():
    assert ServiceClient._parse_rgb("#DC2800") == (220, 40, 0)


def test_set_neopixel_forwards_color_to_animate():
    client = ServiceClient({"neopixel": "http://127.0.0.1:8092/neopixel"})
    with patch.object(client, "animate_neopixel", return_value={"ok": True}) as anim:
        client.set_neopixel("PULSE", emotions=["anger"], color=[220, 40, 0])
        anim.assert_called_once()
        kwargs = anim.call_args.kwargs
        assert kwargs["color"] == (220, 40, 0)
        assert kwargs["emotions"] == ["anger"]
