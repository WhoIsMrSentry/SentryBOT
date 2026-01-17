from __future__ import annotations
from fastapi import APIRouter, Query
from typing import List, Optional

try:
    from ..services.runner import NeoRunner
except Exception:
    from services.runner import NeoRunner  # type: ignore


def get_router(runner: NeoRunner) -> APIRouter:
    r = APIRouter(prefix="/neopixel")

    @r.get("/healthz")
    def healthz():
        return {"ok": True, "num_leds": runner.driver.num_leds}

    @r.post("/clear")
    def clear():
        runner.clear()
        return {"ok": True}

    @r.post("/fill")
    def fill(r_: int = 0, g: int = 0, b: int = 0):
        runner.fill(r_, g, b)
        return {"ok": True}

    @r.post("/rainbow")
    def rainbow(wait: float = 0.02, cycles: int = 3):
        runner.rainbow(wait=wait, cycles=cycles)
        return {"ok": True}

    @r.post("/theater_chase")
    def theater_chase(r_: int = 255, g: int = 0, b: int = 0, wait: float = 0.05, cycles: int = 10):
        runner.theater_chase(r_, g, b, wait=wait, cycles=cycles)
        return {"ok": True}

    @r.post("/effect")
    def run_effect(name: str = Query(..., description="effect name: rainbow|theater_chase|fill|clear")):
        name = name.lower()
        if name == "clear":
            runner.clear()
        elif name == "fill":
            runner.fill(255, 255, 255)
        elif name == "rainbow":
            runner.rainbow()
        elif name == "theater_chase":
            runner.theater_chase()
        else:
            return {"ok": False, "error": "unknown effect"}
        return {"ok": True}

    # Emote: parse text or list of emotions and show colors
    @r.post("/emote")
    def emote(
        text: Optional[str] = None,
        emotions: Optional[List[str]] = Query(None, description="Explicit emotions list"),
        duration: float = 0.25,
    ):
        seq: List[str]
        if emotions:
            seq = [e.lower() for e in emotions]
        elif text:
            # naive extraction: check known keywords from a canonical list
            keywords = [
                'admiration','neutral','surprise','sadness','remorse','relief','realization','pride','optimism',
                'nervousness','love','joy','grief','gratitude','fear','excitement','embarrassment','disgust',
                'disapproval','disappointment','desire','curiosity','confusion','caring','approval','annoyance',
                'anger','amusement'
            ]
            low = text.lower()
            seq = [k for k in keywords if k in low]
            if not seq:
                seq = ["neutral"]
        else:
            seq = ["neutral"]
        # Collect names if available
        try:
            from modules.neopixel.emotions.loader import EmotionStore  # type: ignore
        except Exception:
            from ..emotions.loader import EmotionStore  # type: ignore
        store = EmotionStore()
        chosen = []
        for emo in seq:
            entry = store.random_entry(emo)
            chosen.append({"emotion": emo, "name": entry.name, "rgb": entry.color})
            runner.show_color(*entry.color, duration=duration, clear_after=False)
        return {"ok": True, "emotions": seq, "chosen": chosen}

    @r.post("/emote_named")
    def emote_named(emotion: str, name: str, duration: float = 0.25):
        try:
            from modules.neopixel.emotions.loader import EmotionStore  # type: ignore
        except Exception:
            from ..emotions.loader import EmotionStore  # type: ignore
        store = EmotionStore()
        entry = store.get_by_name(emotion, name)
        if not entry:
            return {"ok": False, "error": "not found"}
        runner.show_color(*entry.color, duration=duration, clear_after=False)
        return {"ok": True, "emotion": emotion, "name": entry.name, "rgb": entry.color}

    @r.post("/animate")
    def animate(
        name: str,
        emotions: Optional[List[str]] = Query(None),
        r: int | None = None,
        g: int | None = None,
        b: int | None = None,
        iterations: int | None = None,
    ):
        color = (r, g, b) if r is not None and g is not None and b is not None else None
        runner.animate(name, emotions=emotions, iterations=iterations, color=color)
        return {"ok": True, "name": name, "emotions": emotions, "color": color, "iterations": iterations}

    return r
