from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from ..contract import (
    SERVO_COUNT,
    build_buzzer_cmd,
    build_cute_cmd,
    build_drive_cmd,
    build_laser_cmd,
    build_liveliness_cmd,
    build_pid_enable_cmd,
    build_policy_cmd,
    build_set_pose_cmd,
    build_set_servo_cmd,
    build_simple_cmd,
    build_sound_output_cmd,
    build_sound_play_cmd,
    build_stepper_cfg_cmd,
    build_stepper_cmd,
    build_track_cmd,
    build_tune_cmd,
    build_zero_set_cmd,
)


class FirmwareHelpersMixin:
    """High-level firmware commands and helpers for xArduinoSerialService."""

    CUTE_SOUND_CATALOG: Dict[str, Dict[str, Any]]
    EMOTION_TO_CUTE: Dict[str, str]
    _last_hb: float
    request: Callable[..., Any]
    send: Callable[..., Any]

    def hello(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("hello"))

    def heartbeat(self) -> None:
        self.send(build_simple_cmd("hb"))
        self._last_hb = time.time()

    def telemetry_start(self, interval_ms: int) -> Dict[str, Any]:
        payload = build_simple_cmd("telemetry_start")
        payload["interval_ms"] = int(interval_ms)
        return self.request(payload)

    def telemetry_stop(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("telemetry_stop"))

    def set_servo(
        self, index: int, deg: float, wait_ack: bool = True, source: str = "autonomy"
    ) -> Dict[str, Any]:
        cmd = build_set_servo_cmd(index, deg)
        if not wait_ack:
            self.send(cmd, source=source)
            return {"ok": True, "cmd": "set_servo", "async": True}
        return self.request(cmd, source=source)

    def set_pose(
        self,
        pose: List[int],
        duration_ms: Optional[int] = None,
        wait_ack: bool = True,
        source: str = "autonomy",
    ) -> Dict[str, Any]:
        if len(pose) != SERVO_COUNT:
            raise ValueError(
                f"pose must be a list of {SERVO_COUNT} integers (servo degrees)"
            )
        payload = build_set_pose_cmd(pose, duration_ms=duration_ms)
        if not wait_ack:
            self.send(payload, source=source)
            return {"ok": True, "cmd": "set_pose", "async": True}
        return self.request(payload, source=source)

    def stepper(
        self, id_: int, mode: str, value: int, drive: Optional[int] = None
    ) -> Dict[str, Any]:
        payload = build_stepper_cmd(id_=id_, mode=mode, value=value, drive=drive)
        return self.request(payload)

    def get_state(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("get_state"))

    def estop(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("estop"))

    def stepper_cfg(
        self, maxSpeed: Optional[int] = None, accel: Optional[int] = None
    ) -> Dict[str, Any]:
        payload = build_stepper_cfg_cmd(max_speed=maxSpeed, accel=accel)
        return self.request(payload)

    def home(self, timeout: float = 10.0) -> Dict[str, Any]:
        return self.request(build_simple_cmd("home"), timeout=timeout)

    def zero_now(self, timeout: float = 2.0) -> Dict[str, Any]:
        return self.request(build_simple_cmd("zero_now"), timeout=timeout)

    def zero_set(self, p1: int, p2: int, timeout: float = 2.0) -> Dict[str, Any]:
        return self.request(build_zero_set_cmd(p1=p1, p2=p2), timeout=timeout)

    def pid(self, enable: bool) -> Dict[str, Any]:
        en = bool(enable)
        r0 = self.request(build_pid_enable_cmd(id_=0, enable=en))
        r1 = self.request(build_pid_enable_cmd(id_=1, enable=en))
        return {
            "ok": bool(r0.get("ok")) and bool(r1.get("ok")),
            "motor0": r0,
            "motor1": r1,
        }

    def stand(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("stand"))

    def sit(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("sit"))

    def imu_read(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("imu_read"))

    def imu_cal(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("imu_cal"))

    def eeprom_save(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("eeprom_save"))

    def eeprom_load(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("eeprom_load"))

    def calibrate(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("calibrate"))

    def tune(
        self,
        pid: Optional[Dict[str, Any]] = None,
        skate: Optional[Dict[str, Any]] = None,
        servoSpeed: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload = build_tune_cmd(pid=pid, skate=skate, servo_speed=servoSpeed)
        return self.request(payload)

    def policy(
        self, pose: Optional[List[int]] = None, steppers: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        payload = build_policy_cmd()
        if pose is not None:
            if len(pose) != SERVO_COUNT:
                raise ValueError(f"pose must have {SERVO_COUNT} elements")
            payload["pose"] = pose
        if steppers is not None:
            if len(steppers) != 2:
                raise ValueError("steppers must have 2 elements")
            payload["steppers"] = steppers
        return self.request(payload)

    def track(self, **kwargs: Any) -> Dict[str, Any]:
        payload = build_track_cmd(
            head_tilt=kwargs.get("head_tilt"),
            head_pan=kwargs.get("head_pan"),
            drive=kwargs.get("drive"),
            tilt=kwargs.get("tilt"),
            pan=kwargs.get("pan"),
        )
        payload.update(
            {k: v for k, v in kwargs.items() if v is not None and k not in payload}
        )
        return self.request(payload)

    def drive(self, value: int) -> Dict[str, Any]:
        return self.request(build_drive_cmd(value=value))

    def liveliness_start(
        self,
        mode: str = "breathe",
        amplitude_deg: Optional[float] = None,
        period_ms: Optional[int] = None,
        pan_center: Optional[float] = None,
        tilt_center: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self.request(
            build_liveliness_cmd(
                True,
                mode=mode,
                amplitude_deg=amplitude_deg,
                period_ms=period_ms,
                pan_center=pan_center,
                tilt_center=tilt_center,
            )
        )

    def liveliness_stop(self) -> Dict[str, Any]:
        return self.request(build_liveliness_cmd(False))

    def laser_on(self, which: int) -> Dict[str, Any]:
        if which not in (1, 2):
            raise ValueError("which must be 1 or 2")
        return self.request(build_laser_cmd(on=True, id_=which))

    def laser_both_on(self) -> Dict[str, Any]:
        return self.request(build_laser_cmd(on=True, both=True))

    def laser_off(self) -> Dict[str, Any]:
        return self.request(build_laser_cmd(on=False))

    def cute(self, name: str) -> Dict[str, Any]:
        return self.request(build_cute_cmd(name))

    def sound_output(self, mode: str) -> Dict[str, Any]:
        mode_low = str(mode).strip().lower()
        if mode_low not in ("loud", "quiet"):
            raise ValueError("mode must be loud or quiet")
        return self.request(build_sound_output_cmd(mode_low))

    def buzzer(
        self, freq: int = 2200, ms: int = 60, out: Optional[str] = None
    ) -> Dict[str, Any]:
        out_low: Optional[str] = None
        if out is not None:
            out_low = str(out).strip().lower()
            if out_low not in ("loud", "quiet"):
                raise ValueError("out must be loud or quiet")
        payload = build_buzzer_cmd(freq=int(freq), ms=int(ms), out=out_low)
        return self.request(payload)

    def sound_play(self, name: str, out: Optional[str] = None) -> Dict[str, Any]:
        out_low: Optional[str] = None
        if out is not None:
            out_low = str(out).strip().lower()
            if out_low not in ("loud", "quiet"):
                raise ValueError("out must be loud or quiet")
        payload = build_sound_play_cmd(name=str(name), out=out_low)
        return self.request(payload)

    def get_cute_catalog(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "sounds": [
                {"name": name, **cfg} for name, cfg in self.CUTE_SOUND_CATALOG.items()
            ],
            "emotion_map": self.EMOTION_TO_CUTE,
        }

    def play_emotion(self, emotion: str) -> Dict[str, Any]:
        key = str(emotion).strip().lower()
        sound = self.EMOTION_TO_CUTE.get(key)
        if not sound:
            raise ValueError(f"unknown emotion: {emotion}")
        return self.cute(sound)
