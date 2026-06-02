from __future__ import annotations

import json
import threading
import time
import os
import logging
from queue import Queue, Empty
from typing import Any, Dict, Optional, Callable, List
try:
    import requests
except Exception:
    requests = None

from .config_loader import load_config
from .contract import (
    SERVO_COUNT,
    build_buzzer_cmd,
    build_cute_cmd,
    build_drive_cmd,
    build_laser_cmd,
    build_pid_enable_cmd,
    build_policy_cmd,
    build_liveliness_cmd,
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
import json as _json
import pathlib as _pathlib

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
except Exception:  # pragma: no cover
    serial = None  # pyserial optional until installed


class SerialTransport:
    """Thin wrapper around pyserial for dependency injection in tests."""

    def __init__(self, port: str, baudrate: int, timeout: float, write_timeout: float):
        if serial is None:
            raise RuntimeError("pyserial not installed")
        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            write_timeout=write_timeout,
        )

    def readline(self) -> bytes:
        return self._ser.readline()

    def write(self, data: bytes) -> int:
        return self._ser.write(data)

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass


class xArduinoSerialService:
    _class_esp_paused_until: float = 0.0
    _class_esp_pause_logged: bool = False
    _class_esp_fail_streak: int = 0

    """NDJSON tabanlı Arduino seri haberleşme servisi.

    - Her satır bir JSON mesajıdır. `{ "cmd": ... }` gönderilir.
    - Cevaplar da satır sonu ile gelir; `{"ok":true/false,...}`.
    - Arkaplanda okuma thread'i ve opsiyonel heartbeat vardır.
    """

    CUTE_SOUND_CATALOG: Dict[str, Dict[str, Any]] = {
        "connection": {"animation": "PULSE", "color": "0,180,80", "iterations": 1},
        "disconnection": {"animation": "THEATER_CHASE", "color": "220,30,30", "iterations": 1},
        "button_pushed": {"animation": "PULSE", "color": "180,180,180", "iterations": 1},
        "mode1": {"animation": "WAVE", "color": "0,180,255", "iterations": 1},
        "mode2": {"animation": "WAVE", "color": "180,0,255", "iterations": 1},
        "mode3": {"animation": "WAVE", "color": "255,80,0", "iterations": 1},
        "happy": {"animation": "WAVE", "color": "255,220,0", "iterations": 2},
        "happy_short": {"animation": "PULSE", "color": "255,220,0", "iterations": 1},
        "super_happy": {"animation": "RAINBOW", "color": "", "iterations": 1},
        "sad": {"animation": "BREATHE", "color": "0,70,255", "iterations": 2},
        "surprise": {"animation": "TWINKLE", "color": "255,255,255", "iterations": 2},
        "ohooh": {"animation": "THEATER_CHASE", "color": "255,255,255", "iterations": 1},
        "ohooh2": {"animation": "THEATER_CHASE", "color": "255,255,255", "iterations": 2},
        "cuddly": {"animation": "BREATHE", "color": "255,50,150", "iterations": 2},
        "confused": {"animation": "PULSE", "color": "170,0,255", "iterations": 2},
        "sleeping": {"animation": "BREATHE", "color": "20,40,120", "iterations": 2},
        "fart1": {"animation": "ALTERNATING", "color": "20,180,20", "iterations": 2},
        "fart2": {"animation": "ALTERNATING", "color": "40,220,40", "iterations": 2},
        "fart3": {"animation": "ALTERNATING", "color": "10,120,10", "iterations": 2},
        "jump": {"animation": "COMET", "color": "255,255,255", "iterations": 2},
    }

    EMOTION_TO_CUTE: Dict[str, str] = {
        "happy": "happy",
        "super_happy": "super_happy",
        "sad": "sad",
        "surprise": "surprise",
        "confused": "confused",
        "sleeping": "sleeping",
        "connected": "connection",
        "disconnected": "disconnection",
    }

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None, transport_factory: Optional[Callable[..., Any]] = None):
        self._logger = logging.getLogger("arduino_serial.service")
        self.cfg = load_config(base_dir=None, overrides=config_overrides)
        self._transport_mode = str(self.cfg.get("transport", "serial")).strip().lower()
        self._esp_mode = self._transport_mode == "esp_http"
        self._esp_base_url = str(self.cfg.get("esp_base_url", "http://127.0.0.1:8091")).rstrip("/")
        self._esp_request_path = str(self.cfg.get("esp_request_path", "/request"))
        self._esp_send_path = str(self.cfg.get("esp_send_path", "/send"))
        self._esp_health_path = str(self.cfg.get("esp_health_path", "/healthz"))
        self._esp_timeout = float(self.cfg.get("esp_timeout_sec", 1.2) or 1.2)
        self._esp_connect_timeout = float(self.cfg.get("esp_connect_timeout_sec", 0.4) or 0.4)
        self._esp_fail_streak = 0
        self._esp_paused_until = 0.0
        self._esp_pause_after = max(1, int(self.cfg.get("esp_pause_after_failures", 5) or 5))
        self._esp_pause_sec = max(10.0, float(self.cfg.get("esp_pause_sec", 120) or 120))
        self._esp_pause_logged = False
        self._esp_http: Any = None
        if self._esp_mode and requests is not None:
            self._esp_http = requests.Session()
        self.transport_factory = transport_factory or (lambda port, baudrate, timeout, write_timeout: SerialTransport(port, baudrate, timeout, write_timeout))
        self._ser: Optional[SerialTransport] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._rx_queue: "Queue[Dict[str, Any]]" = Queue(maxsize=100)
        self._stop = threading.Event()
        self._hb_thread: Optional[threading.Thread] = None
        self._last_hb = 0.0
        self._rfid_lock = threading.Lock()
        self._last_rfid: Optional[tuple[str, float]] = None
        self._saw_boot_ready = False  # drop one-time boot line from request matching
        self._event_handlers: List[Callable[[Dict[str, Any]], None]] = []
        # metrics
        self._metrics = {"rx_count": 0, "tx_count": 0, "acks_sent": 0}
        # try load external cute mapping
        try:
            mfile = _pathlib.Path(__file__).parent / "config" / "cute_mapping.json"
            if mfile.exists():
                with open(mfile, "r", encoding="utf-8") as fh:
                    self.CUTE_SOUND_CATALOG = _json.load(fh)
        except Exception:
            pass

        # outgoing writer queue and thread
        self._write_queue: "Queue[bytes]" = Queue()
        self._writer_thread = threading.Thread(target=self._writer_loop, name="arduino-writer", daemon=True)
        self._writer_thread.start()

    def _esp_url(self, path: str) -> str:
        p = str(path or "").strip()
        if not p.startswith("/"):
            p = "/" + p
        return f"{self._esp_base_url}{p}"

    def _esp_is_paused(self) -> bool:
        return time.time() < max(self._esp_paused_until, self._class_esp_paused_until)

    def _esp_note_failure(self, exc: Exception) -> None:
        self._class_esp_fail_streak += 1
        if self._class_esp_fail_streak < self._esp_pause_after:
            return
        until = time.time() + self._esp_pause_sec
        self._esp_paused_until = until
        xArduinoSerialService._class_esp_paused_until = until
        if not self._class_esp_pause_logged:
            self._logger.warning(
                "ESP bridge unreachable after %d failures (%s); pausing HTTP for %.0fs",
                self._class_esp_fail_streak,
                exc.__class__.__name__,
                self._esp_pause_sec,
            )
            xArduinoSerialService._class_esp_pause_logged = True

    def _esp_note_success(self) -> None:
        self._esp_fail_streak = 0
        self._esp_paused_until = 0.0
        self._esp_pause_logged = False
        xArduinoSerialService._class_esp_fail_streak = 0
        xArduinoSerialService._class_esp_paused_until = 0.0
        xArduinoSerialService._class_esp_pause_logged = False

    def _esp_post(self, path: str, payload: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if requests is None:
            raise RuntimeError("requests is required for ESP HTTP transport")
        if self._esp_is_paused():
            raise RuntimeError(
                f"ESP bridge paused (unreachable); retry in {max(0, int(self._esp_paused_until - time.time()))}s"
            )
        req_timeout = float(timeout if timeout is not None else self._esp_timeout)
        req_timeout = max(0.05, req_timeout)
        conn_timeout = max(0.05, float(self._esp_connect_timeout))
        client = self._esp_http if self._esp_http is not None else requests
        try:
            resp = client.post(
                self._esp_url(path),
                json=payload,
                params=params,
                timeout=(conn_timeout, req_timeout),
            )
        except Exception as exc:
            self._esp_note_failure(exc)
            raise
        if resp.status_code != 200:
            err = RuntimeError(f"ESP bridge HTTP {resp.status_code}: {resp.text[:200]}")
            self._esp_note_failure(err)
            raise err
        try:
            data = resp.json()
        except Exception as exc:
            wrapped = RuntimeError(f"ESP bridge returned non-JSON payload: {exc}")
            self._esp_note_failure(wrapped)
            raise wrapped from exc
        if not isinstance(data, dict):
            err = RuntimeError("ESP bridge response must be a JSON object")
            self._esp_note_failure(err)
            raise err
        self._esp_note_success()
        return data

    # -------- lifecycle --------
    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return
        if not self._esp_mode:
            self._connect()
        self._stop.clear()
        if not self._esp_mode:
            self._rx_thread = threading.Thread(target=self._reader_loop, name="arduino-rx", daemon=True)
            self._rx_thread.start()
        if self.cfg.get("auto_heartbeat", True):
            self._hb_thread = threading.Thread(target=self._heartbeat_loop, name="arduino-hb", daemon=True)
            self._hb_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
        if self._hb_thread:
            self._hb_thread.join(timeout=1.0)
        if self._esp_http is not None:
            try:
                self._esp_http.close()
            except Exception:
                pass
            self._esp_http = None
        if not self._esp_mode:
            self._disconnect()

    # -------- public api --------
    def send(self, obj: Dict[str, Any]) -> None:
        if self._esp_mode:
            data = self._esp_post(self._esp_send_path, payload=obj, timeout=self._esp_timeout)
            ok = bool(data.get("ok", False))
            if not ok:
                raise RuntimeError(str(data.get("error") or data.get("err") or "esp_send_failed"))
            self._metrics["tx_count"] += 1
            return
        line = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
        # enqueue for writer thread to avoid blocking caller
        self._ensure_connected()
        self._write_queue.put(line)
        self._metrics["tx_count"] += 1

    def request(self, obj: Dict[str, Any], timeout: float = 1.0) -> Dict[str, Any]:
        if self._esp_mode:
            max_retries = int(self.cfg.get("request_max_retries", 0) or 0)
            if timeout is None or timeout == 1.0:
                cfg_ms = int(self.cfg.get("request_timeout_ms", 1000) or 1000)
                timeout = float(cfg_ms) / 1000.0
            last_exc: Optional[Exception] = None
            for attempt in range(0, max_retries + 1):
                try:
                    data = self._esp_post(
                        self._esp_request_path,
                        payload=obj,
                        timeout=float(timeout),
                        params={"timeout": float(timeout)},
                    )
                    self._metrics["tx_count"] += 1
                    resp = data.get("resp") if isinstance(data, dict) and "resp" in data else data
                    if isinstance(resp, dict):
                        self._ingest_message(resp)
                        return resp
                    raise RuntimeError("ESP bridge response missing 'resp' object")
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        time.sleep(0.05)
                        continue
            if last_exc:
                raise last_exc
            raise TimeoutError("No response from ESP bridge")

        # Support config-driven retries and default timeout
        max_retries = int(self.cfg.get("request_max_retries", 0) or 0)
        # allow per-call timeout (seconds); if caller passed default, prefer configured ms
        if timeout is None or timeout == 1.0:
            cfg_ms = int(self.cfg.get("request_timeout_ms", 1000) or 1000)
            timeout = float(cfg_ms) / 1000.0

        want_cmd = obj.get("cmd")
        last_exc: Optional[Exception] = None
        echo_samples: List[str] = []
        for attempt in range(0, max_retries + 1):
            # send each attempt
            self.send(obj)
            t0 = time.time()
            try:
                while True:
                    elapsed = time.time() - t0
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        break
                    try:
                        msg = self._rx_queue.get(timeout=remaining)
                        # Filter out initial boot "ready" message once, so it doesn't satisfy the first request.
                        if not obj.get("allow_ready", False) and isinstance(msg, dict) and msg.get("ok") is True and msg.get("msg") == "ready":
                            if not self._saw_boot_ready:
                                self._saw_boot_ready = True
                                continue
                        # Ignore heartbeat acks unless we explicitly requested hb
                        if want_cmd != "hb" and isinstance(msg, dict) and msg.get("ok") is True and msg.get("msg") == "hb":
                            continue
                        # Echo-only frames (e.g. {"cmd":"hello"}) indicate a line echo or wrong peer.
                        # Keep waiting for an explicit ACK/ERR, but remember samples for diagnostics.
                        if isinstance(msg, dict) and ("ok" not in msg and "err" not in msg):
                            if msg.get("cmd") == want_cmd and len(echo_samples) < 3:
                                try:
                                    echo_samples.append(json.dumps(msg, separators=(",", ":")))
                                except Exception:
                                    echo_samples.append(str(msg))
                            continue
                        if isinstance(msg, dict) and ("ok" in msg or "err" in msg):
                            return msg
                        continue
                    except Empty:
                        # no message in remaining interval, will check overall timeout
                        pass
                # timed out for this attempt
                if echo_samples:
                    sample = "; ".join(echo_samples)
                    last_exc = TimeoutError(
                        "No ACK/ERR from Arduino for cmd '%s' (attempt %d). Echo-like frame(s) seen: %s. "
                        "Check serial port selection and disable UART login shell if /dev/serial0 is in use."
                        % (want_cmd, attempt + 1, sample)
                    )
                else:
                    last_exc = TimeoutError("No response from Arduino (attempt %d)" % (attempt + 1))
            except Exception as exc:
                last_exc = exc

            # if we get here, attempt failed; if more retries remain, backoff briefly and retry
            if attempt < max_retries:
                time.sleep(0.05)
                continue

        # all attempts exhausted
        if last_exc:
            raise last_exc
        raise TimeoutError("No response from Arduino")

    def try_get(self, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        try:
            return self._rx_queue.get(timeout=timeout)
        except Empty:
            return None

    def register_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        if handler is None:
            return
        self._event_handlers.append(handler)

    # High-level helpers matching firmware
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

    def set_servo(self, index: int, deg: float) -> Dict[str, Any]:
        return self.request(build_set_servo_cmd(index, deg))

    def set_pose(self, pose: List[int], duration_ms: Optional[int] = None) -> Dict[str, Any]:
        if len(pose) != SERVO_COUNT:
            raise ValueError(f"pose must be a list of {SERVO_COUNT} integers (servo degrees)")
        payload = build_set_pose_cmd(pose, duration_ms=duration_ms)
        return self.request(payload)

    def stepper(self, id_: int, mode: str, value: int, drive: Optional[int] = None) -> Dict[str, Any]:
        payload = build_stepper_cmd(id_=id_, mode=mode, value=value, drive=drive)
        return self.request(payload)

    def get_state(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("get_state"))

    def estop(self) -> Dict[str, Any]:
        return self.request(build_simple_cmd("estop"))

    # -------- extended helpers matching firmware README --------
    def leg_ik(self, x: float, side: str = "L") -> Dict[str, Any]:
        raise NotImplementedError("leg_ik is not supported by the current firmware build")

    def stepper_cfg(self, maxSpeed: Optional[int] = None, accel: Optional[int] = None) -> Dict[str, Any]:
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
        # Neutral calibration in firmware
        return self.request(build_simple_cmd("calibrate"))

    def tune(self, pid: Optional[Dict[str, Any]] = None, skate: Optional[Dict[str, Any]] = None, servoSpeed: Optional[float] = None) -> Dict[str, Any]:
        payload = build_tune_cmd(pid=pid, skate=skate, servo_speed=servoSpeed)
        return self.request(payload)

    def policy(self, pose: Optional[List[int]] = None, steppers: Optional[List[int]] = None) -> Dict[str, Any]:
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
        # Generic passthrough for tracking command (fields depend on firmware build)
        payload = build_track_cmd(
            head_tilt=kwargs.get("head_tilt"),
            head_pan=kwargs.get("head_pan"),
            drive=kwargs.get("drive"),
            tilt=kwargs.get("tilt"),
            pan=kwargs.get("pan"),
        )
        payload.update({k: v for k, v in kwargs.items() if v is not None and k not in payload})
        return self.request(payload)

    def drive(self, value: int) -> Dict[str, Any]:
        return self.request(build_drive_cmd(value=value))

    # -------- liveliness (idle breathing / micro-motion) --------
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

    # -------- laser controls --------
    def laser_on(self, which: int) -> Dict[str, Any]:
        if which not in (1, 2):
            raise ValueError("which must be 1 or 2")
        return self.request(build_laser_cmd(on=True, id_=which))

    def laser_both_on(self) -> Dict[str, Any]:
        return self.request(build_laser_cmd(on=True, both=True))

    def laser_off(self) -> Dict[str, Any]:
        return self.request(build_laser_cmd(on=False))

    # -------- sound controls --------
    def cute(self, name: str) -> Dict[str, Any]:
        return self.request(build_cute_cmd(name))

    def sound_output(self, mode: str) -> Dict[str, Any]:
        mode_low = str(mode).strip().lower()
        if mode_low not in ("loud", "quiet"):
            raise ValueError("mode must be loud or quiet")
        return self.request(build_sound_output_cmd(mode_low))

    def buzzer(self, freq: int = 2200, ms: int = 60, out: Optional[str] = None) -> Dict[str, Any]:
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
                {"name": name, **cfg}
                for name, cfg in self.CUTE_SOUND_CATALOG.items()
            ],
            "emotion_map": self.EMOTION_TO_CUTE,
        }

    def play_emotion(self, emotion: str) -> Dict[str, Any]:
        key = str(emotion).strip().lower()
        sound = self.EMOTION_TO_CUTE.get(key)
        if not sound:
            raise ValueError(f"unknown emotion: {emotion}")
        return self.cute(sound)

    # -------- internals --------
    def _connect(self) -> None:
        port = self._autodetect_port(self.cfg["port"]) if self.cfg.get("port") in (None, "auto", "AUTO") else self.cfg["port"]
        try:
            self._ser = self.transport_factory(
                port,
                int(self.cfg["baudrate"]),
                float(self.cfg["timeout"]),
                float(self.cfg["write_timeout"]),
            )
        except Exception as exc:
            # Provide clearer diagnostic when port cannot be opened
            raise RuntimeError(f"Failed to open serial port {port}: {exc}") from exc

    def _disconnect(self) -> None:
        if self._ser:
            self._ser.close()
            self._ser = None

    def _ensure_connected(self) -> None:
        if self._esp_mode:
            return
        if not self._ser:
            self._connect()

    def _reader_loop(self) -> None:
        assert self._ser is not None
        buf = b""
        while not self._stop.is_set():
            try:
                line = self._ser.readline()
                if not line:
                    continue
                line = line.strip().replace(b"\r", b"")
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                self._ingest_message(msg)
                try:
                    self._rx_queue.put_nowait(msg)
                except Exception:
                    # drop oldest on overflow
                    try:
                        _ = self._rx_queue.get_nowait()
                        self._rx_queue.put_nowait(msg)
                    except Exception:
                        pass
            except Exception:
                time.sleep(0.05)
                continue

    def _heartbeat_loop(self) -> None:
        hb_ms = int(self.cfg.get("heartbeat_ms", 100))
        while not self._stop.is_set():
            now = time.time()
            if now - self._last_hb >= hb_ms / 1000.0:
                try:
                    self.heartbeat()
                except Exception:
                    # best-effort
                    pass
            time.sleep(max(0.01, hb_ms / 1000.0 * 0.5))

    def get_last_rfid(self) -> Optional[Dict[str, Any]]:
        with self._rfid_lock:
            if not self._last_rfid:
                return None
            uid, ts = self._last_rfid
        return {"uid": uid, "seen_at": ts, "age_s": max(0.0, time.time() - ts)}

    def authorize_rfid(self, uid: Optional[str] = None, window_s: Optional[float] = None) -> Dict[str, Any]:
        cfg = self.cfg.get("rfid", {}) or {}
        allowed = {self._normalize_uid(x) for x in cfg.get("allowed_uids", []) if x}
        window = float(window_s if window_s is not None else cfg.get("authorize_window_s", 8.0))

        if uid:
            normalized_uid = self._normalize_uid(uid)
            age_s = None
        else:
            snap = self.get_last_rfid()
            if not snap:
                return {"authorized": False, "reason": "no_rfid"}
            normalized_uid = self._normalize_uid(snap.get("uid"))
            age_s = snap.get("age_s")
            if age_s is not None and age_s > window:
                return {"authorized": False, "uid": normalized_uid, "age_s": age_s, "reason": "stale"}

        if not normalized_uid:
            return {"authorized": False, "reason": "invalid_uid"}

        authorized = normalized_uid in allowed if allowed else False
        result: Dict[str, Any] = {"authorized": authorized, "uid": normalized_uid}
        if age_s is not None:
            result["age_s"] = age_s
        if not authorized and allowed:
            result["reason"] = "unauthorized"
        elif not allowed:
            result["reason"] = "no_allowed_uids"
        return result

    def _record_rfid(self, uid: Optional[str]) -> None:
        normalized = self._normalize_uid(uid)
        if not normalized:
            return
        with self._rfid_lock:
            self._last_rfid = (normalized, time.time())

    @staticmethod
    def _normalize_uid(uid: Optional[str]) -> Optional[str]:
        if not uid:
            return None
        cleaned = str(uid).strip().upper()
        return cleaned or None

    def _ingest_message(self, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        self._metrics["rx_count"] += 1
        event_name = msg.get("event")
        # If Arduino requested a neopixel animation, ACK its seq back so firmware can clear pending
        if event_name == "neopixel_request":
            seq = msg.get("seq")
            try:
                if seq is not None:
                    # best-effort ACK immediately
                    try:
                        self._write_queue.put(( _json.dumps({"ok": True, "ack_seq": int(seq)}) + "\n" ).encode("utf-8"))
                        self._metrics["acks_sent"] += 1
                        # Emit telemetry event for ACK if configured
                        try:
                            self._emit_telemetry_event("arduino_ack", {"seq": int(seq)})
                        except Exception:
                            pass
                    except Exception:
                        # swallow errors; ACK is best-effort
                        pass
            except Exception:
                pass
        if event_name == "rfid":
            self._record_rfid(msg.get("uid"))
            try:
                self._emit_telemetry_event("arduino_rfid", {"uid": msg.get("uid")})
            except Exception:
                pass
        if event_name:
            for handler in list(self._event_handlers):
                try:
                    handler(msg)
                except Exception as exc:
                    self._logger.debug("event handler failed: %s", exc)
        # emit telemetry for critical events like estop
        if msg.get("cmd") == "estop" or event_name == "estop":
            try:
                self._emit_telemetry_event("arduino_estop", msg)
            except Exception:
                pass
        if msg.get("telemetry") and msg.get("rfid"):
            self._record_rfid(msg.get("rfid"))

    # Port autodetect on Windows: prefer Arduino Mega (2560)
    @staticmethod
    def _autodetect_port(fallback: Optional[str]) -> str:
        if serial is None:
            if fallback:
                return fallback
            raise RuntimeError("pyserial not installed")
        ports = list(serial.tools.list_ports.comports())

        def _text(v: Any) -> str:
            return str(v or "").lower()

        def _is_arduino_like(p: Any) -> bool:
            txt = " ".join([
                _text(getattr(p, "description", "")),
                _text(getattr(p, "manufacturer", "")),
                _text(getattr(p, "product", "")),
                _text(getattr(p, "hwid", "")),
            ])
            keys = ("arduino", "mega", "2560", "ch340", "cp210", "usb serial")
            return any(k in txt for k in keys)

        # 1) Prefer Arduino-like USB serial adapters first.
        for p in ports:
            dev = str(getattr(p, "device", "") or "")
            if dev and any(x in dev for x in ("ttyACM", "ttyUSB", "COM")) and _is_arduino_like(p):
                return dev

        # 2) Then any USB serial-style device.
        for p in ports:
            dev = str(getattr(p, "device", "") or "")
            if dev and any(x in dev for x in ("ttyACM", "ttyUSB", "COM")):
                return dev

        # 3) Prefer known UART names if no USB serial device is found.
        for p in ports:
            dev = str(getattr(p, "device", "") or "")
            if any(x in dev for x in ("/dev/ttyAMA0", "/dev/serial0", "/dev/ttyS0")):
                return dev

        # 4) Any port that identifies as Arduino-like.
        for p in ports:
            if _is_arduino_like(p):
                dev = str(getattr(p, "device", "") or "")
                if dev:
                    return dev

        # 5) If Raspberry Pi UART path exists, use it as last Linux fallback.
        try:
            if os.path.exists("/dev/serial0"):
                return "/dev/serial0"
        except Exception:
            pass

        # Fallback: return provided fallback, first discovered port, or a sensible default
        if ports:
            first = str(getattr(ports[0], "device", "") or "")
            if first:
                return first
        if fallback:
            return fallback
        return "COM3" if os.name == "nt" else "/dev/serial0"

    def _writer_loop(self) -> None:
        # background thread to serialize writes to serial port
        while True:
            try:
                data = self._write_queue.get()
                if data is None:
                    break
                try:
                    self._ensure_connected()
                    if self._ser:
                        self._ser.write(data)
                except Exception:
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.01)
                continue

    def _emit_telemetry_event(self, event_type: str, payload: dict) -> None:
        try:
            cfg = self.cfg.get("telemetry", {}) or {}
            if not cfg.get("enabled", False):
                return
            endpoint = cfg.get("endpoint")
            if not endpoint:
                return
            if requests is None:
                return
            body = {"type": event_type, "payload": payload, "ts": time.time()}
            # best-effort, no raise
            try:
                requests.post(endpoint, json=body, timeout=0.5)
            except Exception:
                pass
        except Exception:
            pass
