from __future__ import annotations

from typing import Any, Dict, Optional

from .contract_validators import (
    SERVO_INDEX_PAN,
    SERVO_INDEX_TILT,
    SERVO_INDEX_EAR_L,
    SERVO_INDEX_EAR_R,
    SERVO_COUNT,
    SERVO_MIN_DEG,
    SERVO_MAX_DEG,
    SERVO_BOUNDS,
    LIVELINESS_MODES,
    LIVELINESS_AMPLITUDE_MAX_DEG,
    LIVELINESS_PERIOD_MIN_MS,
    SIMPLE_CMDS,
    PID_ACTION_CMDS,
    _as_int,
    _as_float,
    _is_bool,
    _validate_pose_values,
    _validate_stepper_id,
    _validate_ack_seq,
    _validate_set_servo,
    _validate_set_pose,
    _validate_stepper,
    _validate_zero_set,
    _validate_stepper_cfg,
    _validate_pid_enable,
    _validate_pid_set,
    _validate_pid_action,
    _validate_policy,
    _validate_tune,
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
    _VALIDATORS,
    validate_arduino_payload,
    validate_set_servo_cmd,
    validate_liveliness_cmd,
)


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


def build_pid_set_cmd(
    id_: int,
    *,
    target: Optional[float] = None,
    kp: Optional[float] = None,
    ki: Optional[float] = None,
    kd: Optional[float] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "pid_set", "id": int(id_)}
    if target is not None:
        payload["target"] = float(target)
    if kp is not None:
        payload["kp"] = float(kp)
    if ki is not None:
        payload["ki"] = float(ki)
    if kd is not None:
        payload["kd"] = float(kd)
    return payload


def build_pid_status_cmd(id_: int) -> Dict[str, Any]:
    return {"cmd": "pid_status", "id": int(id_)}


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
