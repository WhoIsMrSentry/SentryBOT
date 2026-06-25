from __future__ import annotations

from typing import Any, Dict, Optional

SERVO_INDEX_PAN = 0
SERVO_INDEX_TILT = 1
SERVO_COUNT = 4
SERVO_MIN_DEG = 0.0
SERVO_MAX_DEG = 180.0

# Per-index servo bounds matching firmware limits.
# Index 0 (pan): 30-150, Index 1 (tilt): 60-120, Index 2-3 (pi servos): 0-180
SERVO_BOUNDS: list[tuple[float, float]] = [
    (30.0, 150.0),
    (60.0, 120.0),
    (0.0, 180.0),
    (0.0, 180.0),
]

LIVELINESS_MODES = ("breathe", "idle", "micro")
LIVELINESS_AMPLITUDE_MAX_DEG = 30.0
LIVELINESS_PERIOD_MIN_MS = 200

SIMPLE_CMDS: frozenset[str] = frozenset({
    "home", "zero_now", "calibrate", "stand", "sit",
    "imu_read", "imu_cal", "eeprom_save", "eeprom_load",
    "get_state", "estop", "telemetry_stop", "hello", "hb",
    "rfid_last", "ultra_read", "speech_play",
})


def build_set_servo_cmd(index: int, deg: float) -> Dict[str, Any]:
    return {"cmd": "set_servo", "index": int(index), "deg": float(deg)}


def build_simple_cmd(cmd: str) -> Dict[str, Any]:
    return {"cmd": str(cmd)}


def build_set_pose_cmd(pose: Any, duration_ms: Optional[int] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "set_pose", "pose": list(pose)}
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    return payload


def build_stepper_cmd(id_: int, mode: str, value: Any, drive: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "stepper", "id": int(id_), "mode": str(mode), "value": value}
    if drive is not None:
        payload["drive"] = drive
    return payload


def build_stepper_cfg_cmd(max_speed: Optional[Any] = None, accel: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "stepper_cfg"}
    if max_speed is not None:
        payload["maxSpeed"] = max_speed
    if accel is not None:
        payload["accel"] = accel
    return payload


def build_zero_set_cmd(p1: int, p2: int) -> Dict[str, Any]:
    return {"cmd": "zero_set", "p1": int(p1), "p2": int(p2)}


def build_pid_enable_cmd(id_: int, enable: bool) -> Dict[str, Any]:
    return {"cmd": "pid_enable", "id": int(id_), "enable": bool(enable)}


def build_tune_cmd(pid: Optional[Dict[str, Any]] = None, skate: Optional[Dict[str, Any]] = None, servo_speed: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "tune"}
    if pid is not None:
        payload["pid"] = pid
    if skate is not None:
        payload["skate"] = skate
    if servo_speed is not None:
        payload["servo_speed"] = servo_speed
    return payload


def build_policy_cmd(pose: Optional[Any] = None, steppers: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "policy"}
    if pose is not None:
        payload["pose"] = list(pose)
    if steppers is not None:
        payload["steppers"] = list(steppers)
    return payload


def build_track_cmd(
    head_tilt: Optional[Any] = None,
    head_pan: Optional[Any] = None,
    drive: Optional[Any] = None,
    tilt: Optional[Any] = None,
    pan: Optional[Any] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "track"}
    if head_tilt is not None:
        payload["head_tilt"] = head_tilt
    if head_pan is not None:
        payload["head_pan"] = head_pan
    if tilt is not None:
        payload["tilt"] = tilt
    if pan is not None:
        payload["pan"] = pan
    if drive is not None:
        payload["drive"] = drive
    return payload


def build_drive_cmd(value: Any) -> Dict[str, Any]:
    return {"cmd": "drive", "value": value}


def build_liveliness_cmd(
    enable: bool,
    mode: str = "breathe",
    amplitude_deg: Optional[float] = None,
    period_ms: Optional[int] = None,
    pan_center: Optional[float] = None,
    tilt_center: Optional[float] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "liveliness", "enable": bool(enable)}
    if mode is not None:
        payload["mode"] = str(mode)
    if amplitude_deg is not None:
        payload["amplitude_deg"] = float(amplitude_deg)
    if period_ms is not None:
        payload["period_ms"] = int(period_ms)
    if pan_center is not None:
        payload["pan_center"] = float(pan_center)
    if tilt_center is not None:
        payload["tilt_center"] = float(tilt_center)
    return payload


def build_laser_cmd(on: bool, id_: Optional[int] = None, both: Optional[bool] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "laser", "on": bool(on)}
    if id_ is not None:
        payload["id"] = int(id_)
    if both is not None:
        payload["both"] = bool(both)
    return payload


def build_cute_cmd(name: str) -> Dict[str, Any]:
    return {"cmd": "cute", "name": str(name)}


def build_sound_output_cmd(mode: str) -> Dict[str, Any]:
    return {"cmd": "sound", "out": str(mode).strip().lower()}


def build_buzzer_cmd(freq: Any = 2200, ms: Any = 60, out: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "buzzer", "freq": int(freq), "ms": int(ms)}
    if out is not None:
        payload["out"] = str(out).strip().lower()
    return payload


def build_sound_play_cmd(name: str, out: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "sound_play", "name": str(name)}
    if out is not None:
        payload["out"] = str(out).strip().lower()
    return payload


def build_lcd_cmd(id_: Optional[int] = None, msg: Optional[str] = None, top: Optional[str] = None, bottom: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "lcd"}
    if id_ is not None:
        payload["id"] = int(id_)
    if msg is not None:
        payload["msg"] = str(msg)
    if top is not None:
        payload["top"] = str(top)
    if bottom is not None:
        payload["bottom"] = str(bottom)
    return payload


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


def _validate_pose_values(pose: Any, field_name: str) -> Optional[str]:
    if not isinstance(pose, list):
        return f"{field_name} must be a list"
    if len(pose) != SERVO_COUNT:
        return f"{field_name} must have exactly {SERVO_COUNT} values"
    for idx, v in enumerate(pose):
        deg = _as_float(v)
        if deg is None:
            return f"{field_name}[{idx}] must be numeric"
        lo, hi = SERVO_BOUNDS[idx] if idx < len(SERVO_BOUNDS) else (SERVO_MIN_DEG, SERVO_MAX_DEG)
        if deg < lo or deg > hi:
            return f"{field_name}[{idx}] must be in [{int(lo)},{int(hi)}]"
    return None


def _validate_stepper_id(payload: Dict[str, Any]) -> Optional[str]:
    if "id" not in payload:
        return None
    sid = _as_int(payload.get("id"))
    if sid is None:
        return "'id' must be an integer"
    if sid not in (0, 1):
        return "'id' must be 0 or 1"
    return None


# ---- per-command validators ----

def _validate_ack_seq(payload: Dict[str, Any]) -> Optional[str]:
    ack_seq = _as_int(payload.get("ack_seq"))
    if ack_seq is None or ack_seq <= 0:
        return "'ack_seq' must be a positive integer"
    if "ok" in payload and not _is_bool(payload.get("ok")):
        return "'ok' must be boolean"
    return None


def _validate_set_servo(payload: Dict[str, Any]) -> Optional[str]:
    if "index" not in payload:
        return "set_servo requires 'index'"
    if "deg" not in payload:
        return "set_servo requires 'deg'"
    try:
        index = int(payload.get("index"))
    except Exception:
        return "set_servo 'index' must be an integer"
    try:
        deg = float(payload.get("deg"))
    except Exception:
        return "set_servo 'deg' must be numeric"
    if index < 0 or index >= SERVO_COUNT:
        return f"set_servo 'index' must be in [0,{SERVO_COUNT - 1}]"
    lo, hi = SERVO_BOUNDS[index] if index < len(SERVO_BOUNDS) else (SERVO_MIN_DEG, SERVO_MAX_DEG)
    if deg < lo or deg > hi:
        return f"set_servo 'deg' must be in [{int(lo)},{int(hi)}] for index {index}"
    return None


def _validate_set_pose(payload: Dict[str, Any]) -> Optional[str]:
    if "pose" not in payload:
        return "set_pose requires 'pose'"
    err = _validate_pose_values(payload.get("pose"), "pose")
    if err:
        return err
    if "duration_ms" in payload:
        dur = _as_int(payload.get("duration_ms"))
        if dur is None or dur < 0:
            return "set_pose 'duration_ms' must be >= 0"
    return None


def _validate_stepper(payload: Dict[str, Any]) -> Optional[str]:
    mode = payload.get("mode")
    if mode not in ("pos", "vel"):
        return "stepper 'mode' must be 'pos' or 'vel'"
    err = _validate_stepper_id(payload)
    if err:
        return f"stepper {err}"
    if "value" not in payload:
        return "stepper requires 'value'"
    if _as_float(payload.get("value")) is None:
        return "stepper 'value' must be numeric"
    if "drive" in payload and _as_float(payload.get("drive")) is None:
        return "stepper 'drive' must be numeric"
    return None


def _validate_zero_set(payload: Dict[str, Any]) -> Optional[str]:
    p1 = _as_int(payload.get("p1"))
    p2 = _as_int(payload.get("p2"))
    if p1 is None or p2 is None:
        return "zero_set requires integer 'p1' and 'p2'"
    return None


def _validate_stepper_cfg(payload: Dict[str, Any]) -> Optional[str]:
    if "maxSpeed" not in payload and "accel" not in payload:
        return "stepper_cfg requires 'maxSpeed' and/or 'accel'"
    if "maxSpeed" in payload and _as_float(payload.get("maxSpeed")) is None:
        return "stepper_cfg 'maxSpeed' must be numeric"
    if "accel" in payload and _as_float(payload.get("accel")) is None:
        return "stepper_cfg 'accel' must be numeric"
    return None


def _validate_pid_enable(payload: Dict[str, Any]) -> Optional[str]:
    err = _validate_stepper_id(payload)
    if err:
        return f"pid_enable {err}"
    if "enable" not in payload or not _is_bool(payload.get("enable")):
        return "pid_enable requires boolean 'enable'"
    return None


def _validate_pid_set(payload: Dict[str, Any]) -> Optional[str]:
    err = _validate_stepper_id(payload)
    if err:
        return f"pid_set {err}"
    has_any = False
    for key in ("kp", "ki", "kd", "target"):
        if key in payload:
            has_any = True
            if _as_float(payload.get(key)) is None:
                return f"pid_set '{key}' must be numeric"
    if not has_any:
        return "pid_set requires at least one of: kp, ki, kd, target"
    return None


def _validate_pid_action(payload: Dict[str, Any]) -> Optional[str]:
    err = _validate_stepper_id(payload)
    if err:
        return f"{payload.get('cmd')} {err}"
    return None


def _validate_policy(payload: Dict[str, Any]) -> Optional[str]:
    if "pose" in payload:
        err = _validate_pose_values(payload.get("pose"), "policy.pose")
        if err:
            return err
    if "steppers" in payload:
        steppers = payload.get("steppers")
        if not isinstance(steppers, list):
            return "policy.steppers must be a list"
        if len(steppers) != 2:
            return "policy.steppers must have exactly 2 values"
        for idx, v in enumerate(steppers):
            if _as_float(v) is None:
                return f"policy.steppers[{idx}] must be numeric"
    if "pose" not in payload and "steppers" not in payload:
        return "policy requires 'pose' and/or 'steppers'"
    return None


def _validate_tune(payload: Dict[str, Any]) -> Optional[str]:
    has_any = False
    if "servo_speed" in payload:
        has_any = True
        if _as_float(payload.get("servo_speed")) is None:
            return "tune 'servo_speed' must be numeric"
    if "pid" in payload:
        has_any = True
        pid = payload.get("pid")
        if not isinstance(pid, dict):
            return "tune 'pid' must be an object"
        for key in ("kp", "ki", "kd"):
            if key in pid and _as_float(pid.get(key)) is None:
                return f"tune pid.{key} must be numeric"
    if "skate" in payload:
        has_any = True
        skate = payload.get("skate")
        if not isinstance(skate, dict):
            return "tune 'skate' must be an object"
        for key in ("kp", "ki", "kd", "max"):
            if key in skate and _as_float(skate.get(key)) is None:
                return f"tune skate.{key} must be numeric"
    if not has_any:
        return "tune requires 'servo_speed', 'pid', and/or 'skate'"
    return None


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


# ---- command dispatch table ----
_VALIDATORS: dict[str, tuple[str, Any]] = {
    "set_servo": ("_validate_set_servo", _validate_set_servo),
    "set_pose": ("_validate_set_pose", _validate_set_pose),
    "stepper": ("_validate_stepper", _validate_stepper),
    "zero_set": ("_validate_zero_set", _validate_zero_set),
    "stepper_cfg": ("_validate_stepper_cfg", _validate_stepper_cfg),
    "pid_enable": ("_validate_pid_enable", _validate_pid_enable),
    "pid_set": ("_validate_pid_set", _validate_pid_set),
    "policy": ("_validate_policy", _validate_policy),
    "tune": ("_validate_tune", _validate_tune),
    "track": ("_validate_track", _validate_track),
    "drive": ("_validate_drive", _validate_drive),
    "liveliness": ("_validate_liveliness", _validate_liveliness),
    "encoder_calibrate": ("_validate_encoder_calibrate", _validate_encoder_calibrate),
    "telemetry_start": ("_validate_telemetry_start", _validate_telemetry_start),
    "laser": ("_validate_laser", _validate_laser),
    "sound": ("_validate_sound", _validate_sound),
    "buzzer": ("_validate_buzzer", _validate_buzzer),
    "sound_play": ("_validate_sound_play", _validate_sound_play),
    "speech": ("_validate_speech", _validate_speech),
    "cute": ("_validate_cute", _validate_cute),
    "lcd": ("_validate_lcd", _validate_lcd),
    "avoid": ("_validate_avoid", _validate_avoid),
    "ir_key": ("_validate_ir_key", _validate_ir_key),
    "menu_goto": ("_validate_menu_goto", _validate_menu_goto),
    "temp_read": ("_validate_temp_read", _validate_temp_read),
}

PID_ACTION_CMDS: frozenset[str] = frozenset({
    "pid_status", "pid_save", "pid_load", "pid_clear_stall", "pid_reset",
})


def validate_arduino_payload(payload: Dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return "payload must be a JSON object"
    if "ack_seq" in payload:
        return _validate_ack_seq(payload)
    cmd = payload.get("cmd")
    if not isinstance(cmd, str) or not cmd:
        return "payload requires non-empty string 'cmd'"
    if cmd in SIMPLE_CMDS:
        return None
    if cmd in PID_ACTION_CMDS:
        return _validate_pid_action(payload)
    validator = _VALIDATORS.get(cmd)
    if validator is not None:
        return validator[1](payload)
    return f"unsupported cmd '{cmd}'"


def validate_set_servo_cmd(payload: Dict[str, Any]) -> Optional[str]:
    if payload.get("cmd") != "set_servo":
        return None
    return _validate_set_servo(payload)


def validate_liveliness_cmd(payload: Dict[str, Any]) -> Optional[str]:
    if payload.get("cmd") != "liveliness":
        return None
    return _validate_liveliness(payload)
