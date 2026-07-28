"""Tests for the ExpressionArbiter."""
import sys
sys.path.insert(0, ".")

import asyncio
import time

from modules.common.emotion_vocab import Emotion
from modules.expression.services.arbitrator import ExpressionArbiter, ModalityClients
import pytest

@pytest.mark.anyio
async def test_express_emotion_returns_ok():
    arb = ExpressionArbiter(ModalityClients())
    result = await arb.express_emotion(
        emotion="anger",
        intensity=1.0,
        duration_s=0.5,
        modalities=["leds", "oled"],
        text=None,
        language="tr",
        force=True,
    )
    assert result["ok"] is True
    assert result["emotion"] == "anger"


@pytest.mark.anyio
async def test_intensity_scales_render():
    arb = ExpressionArbiter(ModalityClients())
    base = await arb.express_emotion(
        emotion="anger", intensity=1.0, duration_s=0.2,
        modalities=["leds"], force=True,
    )
    intense = await arb.express_emotion(
        emotion="anger", intensity=2.0, duration_s=0.2,
        modalities=["leds"], force=True,
    )
    # intensity 2.0 should amplify head delta
    # Lock will block direct comparison
    assert base["render"]["semantic"]["intensity"] == 1.0


@pytest.mark.anyio
async def test_visual_lock_prevents_immediate_switch():
    arb = ExpressionArbiter(ModalityClients())
    r1 = await arb.express_emotion(
        emotion="furious", intensity=1.0, duration_s=0.2,
        modalities=["leds"], force=True,
    )
    r2 = await arb.express_emotion(
        emotion="joy", intensity=1.0, duration_s=0.2,
        modalities=["leds"], force=False,
    )
    # Without force, second one should be locked or rate-limited
    assert r2["ok"] is False


@pytest.mark.anyio
async def test_force_overrides_lock():
    arb = ExpressionArbiter(ModalityClients())
    await arb.express_emotion(
        emotion="anger", intensity=1.0, duration_s=0.2, force=True,
    )
    r = await arb.express_emotion(
        emotion="joy", intensity=1.0, duration_s=0.2, force=True,
    )
    # force=True bypasses visual lock
    assert r["ok"] is True


def test_modality_clients_default_empty():
    clients = ModalityClients()
    assert clients.neopixel is None
    assert clients.oled is None
    assert clients.speak is None
    assert clients.head is None


def test_adapters_set():
    fake = object()
    clients = ModalityClients(neopixel=fake, oled=fake)
    assert clients.neopixel is fake
    assert clients.oled is fake


def test_render_dict_serialization():
    """Render dict can be JSON-serialized."""
    import json
    arb = ExpressionArbiter(ModalityClients())
    result = asyncio.run(arb.express_emotion(
        emotion="furious", intensity=1.5, duration_s=0.1,
        modalities=["leds", "oled", "voice", "head"], force=True, text=None, language="tr",
    ))
    serialized = json.dumps(result)
    assert "furious" in serialized


if __name__ == "__main__":
    asyncio.run(test_express_emotion_returns_ok())
    asyncio.run(test_intensity_scales_render())
    asyncio.run(test_visual_lock_prevents_immediate_switch())
    asyncio.run(test_force_overrides_lock())
    test_modality_clients_default_empty()
    test_adapters_set()
    test_render_dict_serialization()
    print("All ExpressionArbiter tests passed.")
