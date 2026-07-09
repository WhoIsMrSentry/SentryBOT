from __future__ import annotations
from fastapi import APIRouter, Query, Body
from pydantic import BaseModel, Field
from typing import List, Optional

try:
    from ..services.runner import NeoRunner
except Exception:
    from services.runner import NeoRunner  # type: ignore


# Pydantic models and helpers at module scope to avoid OpenAPI forward-ref issues
class AnimationInfo(BaseModel):
    name: str = Field(..., description="Internal animation key (use this when calling /animate)")
    title: str = Field(..., description="Human-friendly title shown in UI")


class AnimationsResponse(BaseModel):
    ok: bool
    animations: List[AnimationInfo]


class AnimateRequest(BaseModel):
    name: str = Field(
        ...,
        description="Animation key. Use /neopixel/animations to pick one",
        json_schema_extra={"example": "WAVE"},
    )
    color: Optional[str] = Field(None, description='Color as "R,G,B" or "#RRGGBB" (optional)')
    r: Optional[int] = Field(None, ge=0, le=255, description="Red channel (0-255)")
    g: Optional[int] = Field(None, ge=0, le=255, description="Green channel (0-255)")
    b: Optional[int] = Field(None, ge=0, le=255, description="Blue channel (0-255)")
    emotions: Optional[List[str]] = Field(None, description="Optional list of emotion names to pick colors from")
    iterations: Optional[int] = Field(None, description="How many iterations/repeats")
    segment: Optional[str] = Field(None, description="Optional segment name (e.g. jewel, stick)")


class PresetUpsertRequest(BaseModel):
    name: str = Field(..., description="Preset name")
    spec: dict = Field(..., description="Preset segment mapping")


class EmotionsResponse(BaseModel):
    ok: bool
    emotions: List[str]


class CompanionModeRequest(BaseModel):
    mode: str = Field(..., description="off | vu | listen | thinking | eye")
    eye_color: Optional[str] = Field(None, description='Optional "#RRGGBB" for center eye')


class CompanionVuRequest(BaseModel):
    level: float = Field(..., ge=0.0, le=1.0, description="Audio level 0..1 for stick VU meter")


def _pretty(name: str) -> str:
    s = name.replace('_', ' ').title()
    s = s.replace('M Grad', 'Multi Grad').replace('M Wave', 'Multi Wave')
    s = s.replace('Alt', 'Alternating').replace('Wipe', 'Color Wipe')
    return s


def _recommended_list(all_names: List[str]) -> List[AnimationInfo]:
    preferred = [
        'RAINBOW', 'RAINBOW_CYCLE', 'BREATHE', 'METEOR', 'FIRE', 'COMET', 'WAVE', 'PULSE',
        'TWINKLE', 'WIPE', 'THEATER_CHASE', 'SNOW', 'ALTERNATING', 'GRADIENT',
        'BOUNCING_BALL', 'RUNNING_LIGHTS', 'STACKED_BARS'
    ]
    out: List[AnimationInfo] = []
    added = set()
    for n in preferred:
        if n in all_names:
            out.append(AnimationInfo(name=n, title=_pretty(n)))
            added.add(n)
    for n in all_names:
        if n in added:
            continue
        if len(out) >= 30:
            break
        out.append(AnimationInfo(name=n, title=_pretty(n)))
    return out


def _parse_color_fields(req: AnimateRequest):
    if req.r is not None and req.g is not None and req.b is not None:
        return (req.r, req.g, req.b)
    if req.color:
        s = req.color.strip()
        if s.startswith('#') and len(s) >= 7:
            try:
                v = int(s[1:7], 16)
                return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
            except Exception:
                return None
        parts = s.split(',')
        if len(parts) == 3:
            try:
                return (int(parts[0]) & 255, int(parts[1]) & 255, int(parts[2]) & 255)
            except Exception:
                return None
    return None


def get_router(runner: NeoRunner) -> APIRouter:
    r = APIRouter(prefix="/neopixel")
    # Expose available animation names for UI/Swagger (friendly view)
    @r.get("/animations", response_model=AnimationsResponse)
    def list_animations(show_all: bool = Query(False, description="Set true to return full animation list")):
        try:
            from ..services import ANIMATIONS  # type: ignore
        except Exception:
            from .services import ANIMATIONS  # type: ignore
        names = sorted(list(ANIMATIONS.keys()))
        if show_all:
            payload = [AnimationInfo(name=n, title=_pretty(n)) for n in names]
        else:
            payload = _recommended_list(names)
        return {"ok": True, "animations": payload}

    @r.get("/emotions", response_model=EmotionsResponse)
    def list_emotions():
        try:
            from ..emotions.loader import EmotionStore  # type: ignore
        except Exception:
            from .emotions.loader import EmotionStore  # type: ignore
        store = EmotionStore()
        palette = store.load()
        names = sorted(list(palette.entries_by_emotion.keys()))
        return {"ok": True, "emotions": names}

    @r.get("/healthz")
    def healthz():
        return {"ok": True, "num_leds": runner.driver.num_leds}

    @r.get("/segments")
    def segments():
        return {"ok": True, "segments": runner.list_segments()}

    @r.get("/presets")
    def presets():
        return {"ok": True, "presets": runner.list_presets(), "version": runner.preset_version()}

    @r.post("/preset/apply")
    def apply_preset(name: str = Query(..., description="preset name")):
        ok = runner.apply_preset(name)
        if not ok:
            return {"ok": False, "error": "unknown preset", "name": name}
        return {"ok": True, "name": name}

    @r.get("/preset/get")
    def get_preset(name: str = Query(..., description="preset name")):
        data = runner.get_preset(name)
        if data is None:
            return {"ok": False, "error": "unknown preset", "name": name}
        return {"ok": True, "name": name, "spec": data, "version": runner.preset_version()}

    @r.post("/preset/set")
    def set_preset(
        body: PresetUpsertRequest = Body(...),
        persist: bool = Query(True, description="Persist to config file"),
    ):
        ok = runner.set_preset(body.name, body.spec, persist=persist)
        if not ok:
            return {"ok": False, "error": "invalid preset payload"}
        return {"ok": True, "name": body.name, "persisted": bool(persist), "version": runner.preset_version()}

    @r.delete("/preset/delete")
    def delete_preset(
        name: str = Query(..., description="preset name"),
        persist: bool = Query(True, description="Persist to config file"),
    ):
        ok = runner.delete_preset(name, persist=persist)
        if not ok:
            return {"ok": False, "error": "unknown preset", "name": name}
        return {"ok": True, "name": name, "persisted": bool(persist), "version": runner.preset_version()}

    @r.post("/clear")
    def clear():
        runner.clear()
        return {"ok": True}

    @r.post("/fill")
    def fill(r_: int = 0, g: int = 0, b: int = 0, segment: Optional[str] = None):
        if segment:
            ok = runner.fill_segment(segment, r_, g, b)
            if not ok:
                return {"ok": False, "error": "unknown segment", "segment": segment}
        else:
            runner.fill(r_, g, b)
        return {"ok": True}

    @r.post("/segment/clear")
    def clear_segment(name: str = Query(..., description="segment name")):
        ok = runner.clear_segment(name)
        if not ok:
            return {"ok": False, "error": "unknown segment", "segment": name}
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
        emotion: Optional[str] = Query(None, description="Single emotion name (convenience)",),
        duration: float = 0.25,
    ):
        seq: List[str]
        # Priority: single `emotion` param, then list `emotions`, then text parsing
        if emotion:
            seq = [emotion.lower()]
        elif emotions:
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
    def animate(body: AnimateRequest = Body(...)):
        color = _parse_color_fields(body)
        runner.animate(body.name, emotions=body.emotions, iterations=body.iterations, color=color, segment=body.segment)
        return {
            "ok": True,
            "name": body.name,
            "emotions": body.emotions,
            "color": color,
            "iterations": body.iterations,
            "segment": body.segment,
        }

    @r.get("/companion/status")
    def companion_status():
        return {"ok": True, **runner.companion_status()}

    @r.post("/companion/mode")
    def companion_mode(body: CompanionModeRequest = Body(...)):
        if body.eye_color:
            parsed = _parse_color_fields(
                AnimateRequest(name="X", color=body.eye_color, r=None, g=None, b=None)
            )
            if parsed:
                runner.companion_set_eye_color(*parsed)
        ok = runner.companion_set_mode(body.mode)
        return {"ok": ok, "mode": body.mode}

    @r.post("/companion/vu")
    def companion_vu(body: CompanionVuRequest = Body(...)):
        ok = runner.companion_set_vu_level(body.level)
        return {"ok": ok, "level": body.level}

    return r
