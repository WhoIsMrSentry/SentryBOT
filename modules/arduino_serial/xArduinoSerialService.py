from __future__ import annotations

import json
import threading
import time
import os
from queue import Queue, Empty
from typing import Any, Dict, Optional, Callable, List

from .config_loader import load_config

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
    """NDJSON tabanlı Arduino seri haberleşme servisi.

    - Her satır bir JSON mesajıdır. `{ "cmd": ... }` gönderilir.
    - Cevaplar da satır sonu ile gelir; `{"ok":true/false,...}`.
    - Arkaplanda okuma thread'i ve opsiyonel heartbeat vardır.
    """

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None, transport_factory: Optional[Callable[..., Any]] = None):
        self.cfg = load_config(base_dir=None, overrides=config_overrides)
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

    # -------- lifecycle --------
    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._connect()
        self._stop.clear()
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
        self._disconnect()

    # -------- public api --------
    def send(self, obj: Dict[str, Any]) -> None:
        line = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
        self._ensure_connected()
        assert self._ser is not None
        self._ser.write(line)

    def request(self, obj: Dict[str, Any], timeout: float = 1.0) -> Dict[str, Any]:
        self.send(obj)
        t0 = time.time()
        want_cmd = obj.get("cmd")
        while True:
            elapsed = time.time() - t0
            remaining = timeout - elapsed
            if remaining <= 0:
                break
            try:
                msg = self._rx_queue.get(timeout=remaining)
                # Filter out initial boot "ready" message once, so it doesn't satisfy the first request.
                if not obj.get("allow_ready", False) and isinstance(msg, dict) and msg.get("ok") is True and msg.get("msg") == "ready":
                    # Only drop once per service lifecycle
                    if not self._saw_boot_ready:
                        self._saw_boot_ready = True
                        continue
                # Ignore heartbeat acks unless we explicitly requested hb
                if want_cmd != "hb" and isinstance(msg, dict) and msg.get("ok") is True and msg.get("msg") == "hb":
                    continue
                # Prefer messages that look like a command reply: must contain 'ok' or 'err'
                if isinstance(msg, dict) and ("ok" in msg or "err" in msg):
                    return msg
                # Otherwise ignore (likely telemetry) and keep waiting
                continue
            except Empty:
                # timed out waiting for a message in remaining interval; loop will break if overall timeout expired
                pass
        raise TimeoutError("No response from Arduino")

    def try_get(self, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        try:
            return self._rx_queue.get(timeout=timeout)
        except Empty:
            return None

    # High-level helpers matching firmware
    def hello(self) -> Dict[str, Any]:
        return self.request({"cmd": "hello"})

    def heartbeat(self) -> None:
        self.send({"cmd": "hb"})
        self._last_hb = time.time()

    def telemetry_start(self, interval_ms: int) -> Dict[str, Any]:
        return self.request({"cmd": "telemetry_start", "interval_ms": interval_ms})

    def telemetry_stop(self) -> Dict[str, Any]:
        return self.request({"cmd": "telemetry_stop"})

    def set_servo(self, index: int, deg: float) -> Dict[str, Any]:
        return self.request({"cmd": "set_servo", "index": index, "deg": deg})

    def set_pose(self, pose: List[int], duration_ms: Optional[int] = None) -> Dict[str, Any]:
        if len(pose) != 8:
            raise ValueError("pose must be a list of 8 integers (servo degrees)")
        payload: Dict[str, Any] = {"cmd": "set_pose", "pose": pose}
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return self.request(payload)

    def stepper(self, id_: int, mode: str, value: int, drive: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"cmd": "stepper", "id": id_, "mode": mode, "value": value}
        if drive is not None:
            payload["drive"] = drive
        return self.request(payload)

    def get_state(self) -> Dict[str, Any]:
        return self.request({"cmd": "get_state"})

    def estop(self) -> Dict[str, Any]:
        return self.request({"cmd": "estop"})

    # -------- extended helpers matching firmware README --------
    def leg_ik(self, x: float, side: str = "L") -> Dict[str, Any]:
        side = side.upper()
        if side not in ("L", "R"):
            raise ValueError("side must be 'L' or 'R'")
        return self.request({"cmd": "leg_ik", "x": x, "side": side})

    def stepper_cfg(self, maxSpeed: Optional[int] = None, accel: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"cmd": "stepper_cfg"}
        if maxSpeed is not None:
            payload["maxSpeed"] = maxSpeed
        if accel is not None:
            payload["accel"] = accel
        return self.request(payload)

    def home(self, timeout: float = 10.0) -> Dict[str, Any]:
        return self.request({"cmd": "home"}, timeout=timeout)

    def zero_now(self, timeout: float = 2.0) -> Dict[str, Any]:
        return self.request({"cmd": "zero_now"}, timeout=timeout)

    def zero_set(self, p1: int, p2: int, timeout: float = 2.0) -> Dict[str, Any]:
        return self.request({"cmd": "zero_set", "p1": p1, "p2": p2}, timeout=timeout)

    def pid(self, enable: bool) -> Dict[str, Any]:
        return self.request({"cmd": "pid", "enable": bool(enable)})

    def stand(self) -> Dict[str, Any]:
        return self.request({"cmd": "stand"})

    def sit(self) -> Dict[str, Any]:
        return self.request({"cmd": "sit"})

    def imu_read(self) -> Dict[str, Any]:
        return self.request({"cmd": "imu_read"})

    def imu_cal(self) -> Dict[str, Any]:
        return self.request({"cmd": "imu_cal"})

    def eeprom_save(self) -> Dict[str, Any]:
        return self.request({"cmd": "eeprom_save"})

    def eeprom_load(self) -> Dict[str, Any]:
        return self.request({"cmd": "eeprom_load"})

    def calibrate(self) -> Dict[str, Any]:
        # Neutral calibration in firmware
        return self.request({"cmd": "calibrate"})

    def tune(self, pid: Optional[Dict[str, Any]] = None, skate: Optional[Dict[str, Any]] = None, servoSpeed: Optional[float] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"cmd": "tune"}
        if pid is not None:
            payload["pid"] = pid
        if skate is not None:
            payload["skate"] = skate
        if servoSpeed is not None:
            payload["servoSpeed"] = servoSpeed
        return self.request(payload)

    def policy(self, pose: Optional[List[int]] = None, steppers: Optional[List[int]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"cmd": "policy"}
        if pose is not None:
            if len(pose) != 8:
                raise ValueError("pose must have 8 elements")
            payload["pose"] = pose
        if steppers is not None:
            if len(steppers) != 2:
                raise ValueError("steppers must have 2 elements")
            payload["steppers"] = steppers
        return self.request(payload)

    def track(self, **kwargs: Any) -> Dict[str, Any]:
        # Generic passthrough for tracking command (fields depend on firmware build)
        payload: Dict[str, Any] = {"cmd": "track"}
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self.request(payload)

    def drive(self, value: int) -> Dict[str, Any]:
        return self.request({"cmd": "drive", "value": value})

    # -------- laser controls --------
    def laser_on(self, which: int) -> Dict[str, Any]:
        if which not in (1, 2):
            raise ValueError("which must be 1 or 2")
        return self.request({"cmd": "laser", "id": which, "on": True})

    def laser_both_on(self) -> Dict[str, Any]:
        return self.request({"cmd": "laser", "both": True, "on": True})

    def laser_off(self) -> Dict[str, Any]:
        return self.request({"cmd": "laser", "on": False})

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
        if msg.get("event") == "rfid":
            self._record_rfid(msg.get("uid"))
            return
        if msg.get("telemetry") and msg.get("rfid"):
            self._record_rfid(msg.get("rfid"))

    # Port autodetect on Windows: prefer Arduino Mega (2560)
    @staticmethod
    def _autodetect_port(fallback: Optional[str]) -> str:
        if serial is None:
            if fallback:
                return fallback
            raise RuntimeError("pyserial not installed")
        # If the Raspberry Pi hardware UART path exists, prefer it
        try:
            if os.path.exists("/dev/serial0"):
                return "/dev/serial0"
        except Exception:
            pass

        ports = list(serial.tools.list_ports.comports())
        # Prefer common Linux UART device names if present
        for p in ports:
            dev = (p.device or "")
            if any(x in dev for x in ("/dev/ttyAMA0", "/dev/serial0", "/dev/ttyS0", "ttyACM", "ttyUSB")):
                return dev

        # try to find 'Arduino Mega' or '2560' by description
        for p in ports:
            desc = (p.description or "").lower()
            if "mega" in desc or "2560" in desc or "arduino" in desc:
                return p.device

        # Fallback: return provided fallback, first discovered port, or a sensible default
        if ports:
            return ports[0].device
        if fallback:
            return fallback
        return "COM3" if os.name == "nt" else "/dev/serial0"
