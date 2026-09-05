from __future__ import annotations

from typing import Any, Dict, Optional

from .command_validators import (
    LIVELINESS_MODES,
    LIVELINESS_AMPLITUDE_MAX_DEG,
    LIVELINESS_PERIOD_MIN_MS,
    SERVO_MIN_DEG,
    SERVO_MAX_DEG,
    _as_int,
    _as_float,
    _is_bool,
    _validate_track,
    _validate_drive,
    _validate_liveliness,
    _validate_encoder_calibrate,
    _validate_telemetry_start,
    _validate_laser,
    _validate_sound,
    _validate_buzzer,
    _validate_sound_play,
    _validate_speech,
    _validate_cute,
    _validate_lcd,
    _validate_avoid,
    _validate_ir_key,
    _validate_menu_goto,
    _validate_temp_read,
)

SERVO_INDEX_PAN = 0
SERVO_INDEX_TILT = 1
SERVO_INDEX_EAR_L = 2
SERVO_INDEX_EAR_R = 3
SERVO_COUNT = 4

SERVO_BOUNDS: list[tuple[float, float]] = [
    (30.0, 150.0),
    (60.0, 120.0),
    (0.0, 180.0),
    (0.0, 180.0),
]

SIMPLE_CMDS: frozenset[str] = frozenset({
    "home", "zero_now", "calibrate", "stand", "sit",
    "imu_read", "imu_cal", "eeprom_save", "eeprom_load",
    "get_state", "estop", "telemetry_stop", "hello", "hb",
    "rfid_last", "ultra_read", "speech_play",
})

PID_ACTION_CMDS: frozenset[str] = frozenset({
    "pid_status", "pid_save", "pid_load", "pid_clear_stall", "pid_reset",
})


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
