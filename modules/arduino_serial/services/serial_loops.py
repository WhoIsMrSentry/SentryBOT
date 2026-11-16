from __future__ import annotations

import json as _json
from queue import Empty, Full, Queue
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..contract import build_ack_cmd

try:
    import requests
except Exception:
    requests = None


class SerialLoopsMixin:
    """I/O background thread loops and message ingestion for ArduinoSerialService."""

    cfg: Dict[str, Any]
    _stop: threading.Event
    _ser: Any
    _rx_queue: Queue
    _write_queue: Queue
    _metrics: Dict[str, int]
    _last_hb: float
    _event_handlers: List[Callable[[Dict[str, Any]], None]]
    _logger: Any
    _telemetry_queue: Optional[Queue]
    _telemetry_thread: Optional[threading.Thread]

    if TYPE_CHECKING:
        def _ensure_connected(self) -> None: ...
        def heartbeat(self) -> None: ...
        def _record_rfid(self, uid: Any) -> None: ...
        def send(self, obj: Dict[str, Any], source: str = "autonomy", bypass_arbiter: bool = False) -> None: ...
        def _inc_metric(self, key: str, delta: int = 1) -> None: ...

    def _reader_loop(self) -> None:
        assert self._ser is not None
        while not self._stop.is_set():
            try:
                line = self._ser.readline()
                if not line:
                    continue
                line = line.strip().replace(b"\r", b"")
                if not line:
                    continue
                try:
                    msg = _json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                self._ingest_message(msg)
                try:
                    self._rx_queue.put_nowait(msg)
                except Exception:
                    try:
                        _ = self._rx_queue.get_nowait()
                        self._rx_queue.put_nowait(msg)
                    except Exception:
                        pass
            except Exception:
                self._stop.wait(0.05)
                continue

    def _heartbeat_loop(self) -> None:
        hb_ms = int(self.cfg.get("heartbeat_ms", 2000))
        interval_s = max(0.1, hb_ms / 1000.0)
        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._last_hb >= interval_s:
                try:
                    self.heartbeat()
                except Exception as exc:
                    if hasattr(self, "_logger") and self._logger:
                        self._logger.debug("Heartbeat cycle failed: %s", exc)
                    if self._stop.wait(max(2.0, interval_s)):
                        break
                    continue
            if self._stop.wait(max(0.05, interval_s * 0.5)):
                break

    def _writer_loop(self) -> None:
        while not self._stop.is_set():
            try:
                data = self._write_queue.get(timeout=0.1)
                if data is None:
                    break
                try:
                    self._ensure_connected()
                    if self._ser:
                        self._ser.write(data)
                except Exception as exc:
                    if hasattr(self, "_logger") and self._logger:
                        self._logger.debug("Serial write failed: %s", exc)
                    self._stop.wait(0.01)
            except Empty:
                continue
            except Exception:
                self._stop.wait(0.01)
                continue

    def _start_telemetry_worker(self) -> None:
        cfg = self.cfg.get("telemetry", {}) or {}
        if not cfg.get("enabled", False) or not cfg.get("endpoint") or requests is None:
            return
        if self._telemetry_thread is not None and self._telemetry_thread.is_alive():
            return
        self._telemetry_queue = Queue(maxsize=128)
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop,
            name="arduino-telemetry",
            daemon=True,
        )
        self._telemetry_thread.start()

    def _stop_telemetry_worker(self) -> None:
        q = getattr(self, "_telemetry_queue", None)
        t = getattr(self, "_telemetry_thread", None)
        if q is not None:
            try:
                q.put_nowait(None)
            except Full:
                try:
                    q.get_nowait()
                    q.put_nowait(None)
                except Exception:
                    pass
        if t is not None and t.is_alive():
            t.join(timeout=1.0)
        self._telemetry_thread = None

    def _telemetry_loop(self) -> None:
        if requests is None:
            return
        cfg = self.cfg.get("telemetry", {}) or {}
        endpoint = str(cfg.get("endpoint") or "").strip()
        if not endpoint:
            return
        session = requests.Session()
        try:
            while True:
                q = getattr(self, "_telemetry_queue", None)
                if q is None:
                    break
                try:
                    item = q.get(timeout=0.2)
                except Empty:
                    if self._stop.is_set():
                        break
                    continue
                if item is None:
                    break
                try:
                    session.post(endpoint, json=item, timeout=0.5)
                except Exception as exc:
                    if hasattr(self, "_logger") and self._logger:
                        self._logger.debug("telemetry forward failed: %s", exc)
        finally:
            try:
                session.close()
            except Exception:
                pass

    def _ingest_message(self, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        if getattr(self, "watchdog", None) is not None:
            try:
                self.watchdog.feed(source=str(msg.get("event") or msg.get("cmd") or "rx"))
            except Exception:
                pass
        if hasattr(self, "_inc_metric"):
            self._inc_metric("rx_count", 1)
        else:
            self._metrics["rx_count"] += 1
        event_name = msg.get("event")
        if event_name == "neopixel_request":
            seq = msg.get("seq")
            if seq is not None:
                try:
                    ack_seq = int(seq)
                    ack_cmd = build_ack_cmd(ack_seq, ok=True)
                    self.send(ack_cmd, bypass_arbiter=True)
                    if hasattr(self, "_inc_metric"):
                        self._inc_metric("acks_sent", 1)
                    else:
                        self._metrics["acks_sent"] += 1
                    self._emit_telemetry_event("arduino_ack", {"seq": ack_seq})
                except Exception as exc:
                    if hasattr(self, "_logger") and self._logger:
                        self._logger.debug("neopixel ACK failed: %s", exc)
        if event_name == "rfid":
            self._record_rfid(msg.get("uid"))
            self._emit_telemetry_event("arduino_rfid", {"uid": msg.get("uid")})
        if event_name:
            for handler in list(self._event_handlers):
                try:
                    handler(msg)
                except Exception as exc:
                    self._logger.debug("event handler failed: %s", exc)
        if msg.get("cmd") == "estop" or event_name == "estop":
            self._emit_telemetry_event("arduino_estop", msg)
        if msg.get("telemetry") and msg.get("rfid"):
            self._record_rfid(msg.get("rfid"))

    def _emit_telemetry_event(self, event_type: str, payload: dict) -> None:
        cfg = self.cfg.get("telemetry", {}) or {}
        if not cfg.get("enabled", False) or not cfg.get("endpoint") or requests is None:
            return
        body = {"type": event_type, "payload": payload, "ts": time.time()}
        q = getattr(self, "_telemetry_queue", None)
        if q is None:
            self._start_telemetry_worker()
            q = getattr(self, "_telemetry_queue", None)
        if q is not None:
            try:
                q.put_nowait(body)
            except Full:
                try:
                    q.get_nowait()
                    q.put_nowait(body)
                except Exception:
                    pass
