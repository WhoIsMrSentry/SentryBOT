"""Tests for the ExpressionArbiter."""
import sys
sys.path.insert(0, ".")

import asyncio

from modules.expression.semantic.services.arbitrator import ExpressionArbiter, ModalityClients

def test_express_emotion_returns_ok():
    async def run():
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
    asyncio.run(run())


def test_intensity_scales_render():
    async def run():
        seen_speeds: list[float] = []

        class _FakeNeo:
            async def set_effect(self, effect, color, speed=1.0, duration_s=3.0):
                seen_speeds.append(speed)
                return True

        arb = ExpressionArbiter(ModalityClients(neopixel=_FakeNeo()))
        base = await arb.express_emotion(
            emotion="anger", intensity=1.0, duration_s=0.2,
            modalities=["leds"], force=True,
        )
        await asyncio.sleep(0.01)
        subtle = await arb.express_emotion(
            emotion="anger", intensity=0.2, duration_s=0.2,
            modalities=["leds"], force=True,
        )
        await asyncio.sleep(0.01)
        extreme = await arb.express_emotion(
            emotion="anger", intensity=2.0, duration_s=0.2,
            modalities=["leds"], force=True,
        )
        await asyncio.sleep(0.01)
        await arb.stop()
        assert base["render"]["semantic"]["intensity"] == 1.0
        assert subtle["render"]["semantic"]["intensity"] == 0.2
        assert extreme["render"]["semantic"]["intensity"] == 2.0
        assert extreme["render"]["head"]["pan_delta"] == 2 * base["render"]["head"]["pan_delta"]
        # Speed passed to adapter equals render.neopixel.speed (no double scaling)
        assert len(seen_speeds) == 3
        assert seen_speeds[1] == subtle["render"]["neopixel"]["speed"]
    asyncio.run(run())


def test_visual_lock_prevents_immediate_switch():
    async def run():
        arb = ExpressionArbiter(ModalityClients())
        await arb.express_emotion(
            emotion="furious", intensity=1.0, duration_s=0.2,
            modalities=["leds"], force=True,
        )
        r2 = await arb.express_emotion(
            emotion="joy", intensity=1.0, duration_s=0.2,
            modalities=["leds"], force=False,
        )
        assert r2["ok"] is False
    asyncio.run(run())


def test_force_overrides_lock():
    async def run():
        arb = ExpressionArbiter(ModalityClients())
        await arb.express_emotion(
            emotion="anger", intensity=1.0, duration_s=0.2, force=True,
        )
        r = await arb.express_emotion(
            emotion="joy", intensity=1.0, duration_s=0.2, force=True,
        )
        assert r["ok"] is True
    asyncio.run(run())


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
