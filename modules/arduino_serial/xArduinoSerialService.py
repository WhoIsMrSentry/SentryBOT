from __future__ import annotations

import json
import json as _json
import logging
import os
import pathlib as _pathlib
import threading
import time
from queue import Empty, Queue
from typing import Any, Callable, Dict, List, Optional

try:
    import requests
except Exception:
    requests = None

from .config_loader import load_config
from .services.cute_catalog import CUTE_SOUND_CATALOG, EMOTION_TO_CUTE
from .services.rfid_handler import RfidHandlerMixin
from .services.serial_loops import SerialLoopsMixin
from .head_arbiter_integration import HeadArbiterTransportWrapper
from .transports import (
    EspTransportMixin,
    FirmwareHelpersMixin,
    SerialTransport,
    _PI_SERIAL_CANDIDATE_GLOBS,
)

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
except Exception:  # pragma: no cover
    serial = None


from .services.port_detector import (
    _PI_SERIAL_CANDIDATE_GLOBS,
    _existing_device_from_globs,
    _default_serial_device,
    _autodetect_port,
)


class xArduinoSerialService(RfidHandlerMixin, SerialLoopsMixin, EspTransportMixin, FirmwareHelpersMixin):
    """NDJSON tabanlı Arduino seri haberleşme servisi."""

    CUTE_SOUND_CATALOG: Dict[str, Dict[str, Any]] = dict(CUTE_SOUND_CATALOG)
    EMOTION_TO_CUTE: Dict[str, str] = dict(EMOTION_TO_CUTE)

    def __init__(
        self,
        config_overrides: Optional[Dict[str, Any]] = None,
        transport_factory: Optional[Callable[..., Any]] = None,
        head_arbiter: Optional[Any] = None,
        head_arbiter_enabled: bool = True,
        head_arbiter_bypass_for_testing: bool = False,
    ):
        self._logger = logging.getLogger("arduino_serial.service")
        self.cfg = load_config(base_dir=None, overrides=config_overrides)
        self._transport_mode = str(self.cfg.get("transport", "serial")).strip().lower()
        self._esp_mode = self._transport_mode == "esp_http"
        self._esp_base_url = str(
            self.cfg.get("esp_base_url", "http://127.0.0.1:8091")
        ).rstrip("/")
        self._esp_request_path = str(self.cfg.get("esp_request_path", "/request"))
        self._esp_send_path = str(self.cfg.get("esp_send_path", "/send"))
        self._esp_health_path = str(self.cfg.get("esp_health_path", "/healthz"))
        self._esp_timeout = float(self.cfg.get("esp_timeout_sec", 1.2) or 1.2)
        self._esp_connect_timeout = float(
            self.cfg.get("esp_connect_timeout_sec", 0.4) or 0.4
        )
        self._esp_fail_streak = 0
        self._esp_paused_until = 0.0
        self._esp_pause_after = max(
            1, int(self.cfg.get("esp_pause_after_failures", 5) or 5)
        )
        self._esp_pause_sec = max(
            10.0, float(self.cfg.get("esp_pause_sec", 120) or 120)
        )
        self._esp_pause_logged = False
        self._esp_http: Any = None
        if self._esp_mode and requests is not None:
            self._esp_http = requests.Session()
        self.transport_factory = transport_factory or (
            lambda port, baudrate, timeout, write_timeout: SerialTransport(
                port, baudrate, timeout, write_timeout
            )
        )
        self._ser: Optional[SerialTransport] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._rx_queue: "Queue[Dict[str, Any]]" = Queue(maxsize=100)
        self._stop = threading.Event()
        self._hb_thread: Optional[threading.Thread] = None
        self._last_hb = 0.0
        self._rfid_lock = threading.Lock()
        self._last_rfid: Optional[tuple[str, float]] = None
        self._saw_boot_ready = False
        self._request_lock = threading.Lock()
        self._event_handlers: List[Callable[[Dict[str, Any]], None]] = []
        self._metrics = {"rx_count": 0, "tx_count": 0, "acks_sent": 0}

        # HeadControlArbiter integration
        self._head_arbiter_wrapper: Optional[Any] = None
        if head_arbiter is not None:
            self._attach_head_arbiter_wrapper(head_arbiter, bypass_for_testing=head_arbiter_bypass_for_testing)

        try:
            mfile = _pathlib.Path(__file__).parent / "config" / "cute_mapping.json"
            if mfile.exists():
                with open(mfile, "r", encoding="utf-8") as fh:
                    self.CUTE_SOUND_CATALOG = _json.load(fh)
        except Exception:
            pass

        self._write_queue: "Queue[Optional[bytes]]" = Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._request_seq = 0
        self._request_seq_lock = threading.Lock()
        self._started = False
        self._start_writer_thread()

    def _attach_head_arbiter_wrapper(self, head_arbiter: Any, bypass_for_testing: bool = False) -> None:
        from .head_arbiter_integration import HeadArbiterTransportWrapper

        self._head_arbiter_wrapper = HeadArbiterTransportWrapper(
            head_arbiter=head_arbiter,
            enable=True,
            bypass_for_testing=bypass_for_testing,
        )
        self._logger.info("HeadControlArbiter integration enabled")

    def set_head_arbiter(self, head_arbiter: Any) -> None:
        """Swap the transport-level arbiter instance (R1 single-instance fix).

        Keeps exactly one live HeadControlArbiter: when the gateway resolves a
        newer/configured instance, the already-built transport wrapper is
        rebuilt against it instead of silently arbitrating on a stale copy.
        """
        self._attach_head_arbiter_wrapper(head_arbiter)

    def _start_writer_thread(self) -> None:
        """Start or restart the serial writer thread after service restarts."""
        if self._writer_thread is not None and self._writer_thread.is_alive():
            return
        self._write_queue = Queue()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="arduino-tx",
            daemon=True,
        )
        self._writer_thread.start()

    def _next_request_seq(self) -> int:
        with self._request_seq_lock:
            self._request_seq = (int(self._request_seq) + 1) & 0x7FFFFFFF
            if self._request_seq <= 0:
                self._request_seq = 1
            return self._request_seq

    def _prepare_request_payload(self, obj: Dict[str, Any]):
        payload = dict(obj)
        existing = payload.get("seq")
        if existing is not None:
            try:
                return payload, int(existing)
            except Exception:
                return payload, None
        seq = self._next_request_seq()
        payload["seq"] = seq
        return payload, seq

    @staticmethod
    def _response_seq(msg: Dict[str, Any]) -> Optional[int]:
        for key in ("ack_seq", "seq", "request_seq", "req_seq", "id"):
            if key not in msg:
                continue
            try:
                return int(msg.get(key))
            except Exception:
                return None
        return None

    def _response_matches_request(self, msg: Dict[str, Any], want_seq: Optional[int]) -> bool:
        if want_seq is None:
            return True
        got_seq = self._response_seq(msg)
        if got_seq is None:
            # Backward compatible: old firmware may reply {"ok": true} without seq.
            return not bool(self.cfg.get("strict_request_correlation", False))
        return int(got_seq) == int(want_seq)

    # -------- lifecycle --------
    def start(self) -> None:
        if getattr(self, "_started", False):
            return
        self._stop.clear()
        self._start_writer_thread()
        if not self._esp_mode:
            self._connect()
            if not (self._rx_thread and self._rx_thread.is_alive()):
                self._rx_thread = threading.Thread(
                    target=self._reader_loop, name="arduino-rx", daemon=True
                )
                self._rx_thread.start()
        if self.cfg.get("auto_heartbeat", True) and not (
            self._hb_thread and self._hb_thread.is_alive()
        ):
            self._hb_thread = threading.Thread(
                target=self._heartbeat_loop, name="arduino-hb", daemon=True
            )
            self._hb_thread.start()
        self._started = True

    def stop(self) -> None:
        self._started = False
        self._stop.set()
        try:
            self._write_queue.put(None)
        except Exception:
            pass
        if self._writer_thread:
            self._writer_thread.join(timeout=1.0)
            self._writer_thread = None
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
            self._rx_thread = None
        if self._hb_thread:
            self._hb_thread.join(timeout=1.0)
            self._hb_thread = None
        if self._esp_http is not None:
            try:
                self._esp_http.close()
            except Exception:
                pass
            self._esp_http = None
        if not self._esp_mode:
            self._disconnect()

    # -------- public api --------
    def send(self, obj: Dict[str, Any], source: str = "autonomy", bypass_arbiter: bool = False) -> None:
        # Apply HeadControlArbiter for head movement commands
        if not bypass_arbiter and self._head_arbiter_wrapper is not None:
            try:
                obj = self._head_arbiter_wrapper.wrap_command(obj, source=source)
            except RuntimeError as exc:
                self._logger.warning("Head movement denied by arbiter: %s", exc)
                raise
        
        if self._esp_mode:
            data = self._esp_post(
                self._esp_send_path, payload=obj, timeout=self._esp_timeout
            )
            ok = bool(data.get("ok", False))
            if not ok:
                raise RuntimeError(
                    str(data.get("error") or data.get("err") or "esp_send_failed")
                )
            self._metrics["tx_count"] += 1
            return
        line = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
        self._ensure_connected()
        self._write_queue.put(line)
        self._metrics["tx_count"] += 1

    def request(self, obj: Dict[str, Any], timeout: float = 1.0, source: str = "autonomy") -> Dict[str, Any]:
        # Apply HeadControlArbiter for head movement commands
        if self._head_arbiter_wrapper is not None:
            try:
                obj = self._head_arbiter_wrapper.wrap_command(obj, source=source)
            except RuntimeError as exc:
                self._logger.warning("Head movement denied by arbiter: %s", exc)
                raise
        
        with self._request_lock:
            return self._request_locked(obj, timeout)

    def _request_locked(
        self, obj: Dict[str, Any], timeout: float = 1.0
    ) -> Dict[str, Any]:
        request_obj, _want_seq = self._prepare_request_payload(obj)
        if self._esp_mode:
            return self._request_locked_esp(request_obj, timeout)
        return self._request_locked_serial(request_obj, timeout)

    def _request_locked_serial(
        self, obj: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        max_retries = int(self.cfg.get("request_max_retries", 0) or 0)
        if timeout is None or timeout == 1.0:
            cfg_ms = int(self.cfg.get("request_timeout_ms", 1000) or 1000)
            timeout = float(cfg_ms) / 1000.0

        want_cmd = obj.get("cmd")
        try:
            want_seq = int(obj.get("seq")) if obj.get("seq") is not None else None
        except Exception:
            want_seq = None
        last_exc: Optional[Exception] = None
        echo_samples: List[str] = []
        for attempt in range(0, max_retries + 1):
            self.send(obj, bypass_arbiter=True)
            t0 = time.time()
            try:
                while True:
                    elapsed = time.time() - t0
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        break
                    try:
                        msg = self._rx_queue.get(timeout=remaining)
                        if (
                            not obj.get("allow_ready", False)
                            and isinstance(msg, dict)
                            and msg.get("ok") is True
                            and msg.get("msg") == "ready"
                        ):
                            if not self._saw_boot_ready:
                                self._saw_boot_ready = True
                                continue
                        if (
                            want_cmd != "hb"
                            and isinstance(msg, dict)
                            and msg.get("ok") is True
                            and msg.get("msg") == "hb"
                        ):
                            continue
                        if isinstance(msg, dict) and (
                            "ok" not in msg and "err" not in msg
                        ):
                            if msg.get("cmd") == want_cmd and len(echo_samples) < 3:
                                try:
                                    echo_samples.append(
                                        json.dumps(msg, separators=(",", ":"))
                                    )
                                except Exception:
                                    echo_samples.append(str(msg))
                            continue
                        if isinstance(msg, dict) and ("ok" in msg or "err" in msg):
                            if not self._response_matches_request(msg, want_seq):
                                continue
                            return msg
                        continue
                    except Empty:
                        pass
                if echo_samples:
                    sample = "; ".join(echo_samples)
                    last_exc = TimeoutError(
                        "No ACK/ERR from Arduino for cmd '%s' (attempt %d). Echo-like frame(s) seen: %s. "
                        "Check serial port selection and disable UART login shell if /dev/serial0 is in use."
                        % (want_cmd, attempt + 1, sample)
                    )
                else:
                    last_exc = TimeoutError(
                        "No response from Arduino (attempt %d)" % (attempt + 1)
                    )
            except Exception as exc:
                last_exc = exc

            if attempt < max_retries:
                time.sleep(0.05)
                continue

        if last_exc:
            raise last_exc
        raise TimeoutError("No response from Arduino")

    def register_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        if handler is None:
            return
        self._event_handlers.append(handler)

    # -------- internals --------
    def _connect(self) -> None:
        port = (
            self._autodetect_port(self.cfg["port"])
            if self.cfg.get("port") in (None, "auto", "AUTO")
            else self.cfg["port"]
        )
        try:
            self._ser = self.transport_factory(
                port,
                int(self.cfg["baudrate"]),
                float(self.cfg["timeout"]),
                float(self.cfg["write_timeout"]),
            )
        except Exception as exc:
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

    @staticmethod
    def _autodetect_port(fallback: Optional[str]) -> str:
        return _autodetect_port(fallback)

