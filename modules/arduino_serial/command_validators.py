from __future__ import annotations

from typing import Any, Dict, Optional

LIVELINESS_MODES = ("breathe", "idle", "micro")
LIVELINESS_AMPLITUDE_MAX_DEG = 30.0
LIVELINESS_PERIOD_MIN_MS = 200
SERVO_MIN_DEG = 0.0
SERVO_MAX_DEG = 180.0


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _validate_track(payload: Dict[str, Any]) -> Optional[str]:
    has_head = any(k in payload for k in ("head_tilt", "head_pan", "tilt", "pan"))
    if not has_head and "drive" not in payload:
        return "track requires head keys and/or 'drive'"
    for key in ("head_tilt", "head_pan", "tilt", "pan", "drive"):
        if key in payload and _as_float(payload.get(key)) is None:
            return f"track '{key}' must be numeric"
    return None


def _validate_drive(payload: Dict[str, Any]) -> Optional[str]:
    if _as_float(payload.get("value")) is None:
        return "drive requires numeric 'value'"
    return None


def _validate_liveliness(payload: Dict[str, Any]) -> Optional[str]:
    if "enable" not in payload or not _is_bool(payload.get("enable")):
        return "liveliness requires boolean 'enable'"
    if not payload.get("enable"):
        return None
    if "mode" in payload and payload.get("mode") not in LIVELINESS_MODES:
        return f"liveliness 'mode' must be one of {LIVELINESS_MODES}"
    if "amplitude_deg" in payload:
        amp = _as_float(payload.get("amplitude_deg"))
        if amp is None or amp < 0 or amp > LIVELINESS_AMPLITUDE_MAX_DEG:
            return f"liveliness 'amplitude_deg' must be in [0,{int(LIVELINESS_AMPLITUDE_MAX_DEG)}]"
    if "period_ms" in payload:
        period = _as_int(payload.get("period_ms"))
        if period is None or period < LIVELINESS_PERIOD_MIN_MS:
            return f"liveliness 'period_ms' must be >= {LIVELINESS_PERIOD_MIN_MS}"
    for key in ("pan_center", "tilt_center"):
        if key in payload:
            val = _as_float(payload.get(key))
            if val is None or val < SERVO_MIN_DEG or val > SERVO_MAX_DEG:
                return f"liveliness '{key}' must be in [{int(SERVO_MIN_DEG)},{int(SERVO_MAX_DEG)}]"
    return None


def _validate_encoder_calibrate(payload: Dict[str, Any]) -> Optional[str]:
    if "duration_ms" in payload:
        dur = _as_int(payload.get("duration_ms"))
        if dur is None or dur <= 0:
            return "encoder_calibrate 'duration_ms' must be > 0"
    return None


def _validate_telemetry_start(payload: Dict[str, Any]) -> Optional[str]:
    if "interval_ms" in payload:
        interval = _as_int(payload.get("interval_ms"))
        if interval is None or interval <= 0:
            return "telemetry_start 'interval_ms' must be > 0"
    return None


def _validate_laser(payload: Dict[str, Any]) -> Optional[str]:
    if "on" not in payload or not _is_bool(payload.get("on")):
        return "laser requires boolean 'on'"
    if payload.get("on"):
        if payload.get("both") is True:
            return None
        lid = _as_int(payload.get("id"))
        if lid not in (1, 2):
            return "laser requires 'id' as 1 or 2 when 'on' is true and both is not true"
    return None


def _validate_sound(payload: Dict[str, Any]) -> Optional[str]:
    if "out" in payload and payload.get("out") not in ("loud", "quiet"):
        return "sound 'out' must be 'loud' or 'quiet'"
    if "mode" in payload and payload.get("mode") not in ("loud", "quiet"):
        return "sound 'mode' must be 'loud' or 'quiet'"
    if "both" in payload and not _is_bool(payload.get("both")):
        return "sound 'both' must be boolean"
    if "out" not in payload and "mode" not in payload and "both" not in payload:
        return "sound requires one of: out, mode, both"
    return None


def _validate_buzzer(payload: Dict[str, Any]) -> Optional[str]:
    freq = _as_int(payload.get("freq", 2200))
    ms = _as_int(payload.get("ms", 60))
    if freq is None:
        return "buzzer 'freq' must be integer"
    if ms is None:
        return "buzzer 'ms' must be integer"
    if "out" in payload and payload.get("out") not in ("loud", "quiet"):
        return "buzzer 'out' must be 'loud' or 'quiet'"
    return None


def _validate_sound_play(payload: Dict[str, Any]) -> Optional[str]:
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return "sound_play requires non-empty 'name'"
    if "out" in payload and payload.get("out") not in ("loud", "quiet"):
        return "sound_play 'out' must be 'loud' or 'quiet'"
    return None


def _validate_speech(payload: Dict[str, Any]) -> Optional[str]:
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return "speech requires non-empty 'text'"
    return None


def _validate_cute(payload: Dict[str, Any]) -> Optional[str]:
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return "cute requires non-empty 'name'"
    return None


def _validate_lcd(payload: Dict[str, Any]) -> Optional[str]:
    has_msg = any(isinstance(payload.get(k), str) and payload.get(k).strip() for k in ("msg", "top", "bottom"))
    if not has_msg:
        return "lcd requires non-empty 'msg' or 'top'/'bottom'"
    if "id" in payload and _as_int(payload.get("id")) is None:
        return "lcd 'id' must be integer"
    return None


def _validate_avoid(payload: Dict[str, Any]) -> Optional[str]:
    if "enable" not in payload or not _is_bool(payload.get("enable")):
        return "avoid requires boolean 'enable'"
    return None


def _validate_ir_key(payload: Dict[str, Any]) -> Optional[str]:
    if "key" not in payload:
        return "ir_key requires 'key'"
    return None


def _validate_menu_goto(payload: Dict[str, Any]) -> Optional[str]:
    if "menu" not in payload:
        return "menu_goto requires 'menu'"
    return None


def _validate_temp_read(payload: Dict[str, Any]) -> Optional[str]:
    return None
