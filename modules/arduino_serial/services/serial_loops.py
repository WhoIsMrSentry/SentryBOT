from __future__ import annotations

import json as _json
import time
from queue import Empty, Queue
from typing import Any, Callable, Dict, List, Optional

try:
    import requests
except Exception:
    requests = None


class SerialLoopsMixin:
    """I/O background thread loops and message ingestion for ArduinoSerialService."""

    cfg: Dict[str, Any]
    _stop: Any
    _ser: Any
    _rx_queue: Queue
    _write_queue: Queue
    _metrics: Dict[str, Any]
    _last_hb: float
    _event_handlers: List[Callable[[Dict[str, Any]], None]]
    _logger: Any

    def _ensure_connected(self) -> None:
        raise NotImplementedError

    def heartbeat(self) -> Dict[str, Any]:
        raise NotImplementedError

    def _record_rfid(self, uid: Any) -> None:
        raise NotImplementedError

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
                time.sleep(0.05)
                continue

    def _heartbeat_loop(self) -> None:
        hb_ms = int(self.cfg.get("heartbeat_ms", 100))
        interval_s = max(0.1, hb_ms / 1000.0)
        while not self._stop.is_set():
            now = time.time()
            if now - self._last_hb >= interval_s:
                try:
                    self.heartbeat()
                except Exception as exc:
                    if hasattr(self, "_logger") and self._logger:
                        self._logger.debug("Heartbeat cycle failed: %s", exc)
                    # Back off when link is failing
                    time.sleep(max(2.0, interval_s))
                    continue
            time.sleep(max(0.05, interval_s * 0.5))

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
                    time.sleep(0.01)
            except Empty:
                continue
            except Exception:
                time.sleep(0.01)
                continue

    def _ingest_message(self, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        self._metrics["rx_count"] += 1
        event_name = msg.get("event")
        if event_name == "neopixel_request":
            seq = msg.get("seq")
            try:
                if seq is not None:
                    try:
                        self._write_queue.put(
                            (
                                _json.dumps({"ok": True, "ack_seq": int(seq)}) + "\n"
                            ).encode("utf-8")
                        )
                        self._metrics["acks_sent"] += 1
                        try:
                            self._emit_telemetry_event("arduino_ack", {"seq": int(seq)})
                        except Exception:
                            pass
                    except Exception:
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
        if msg.get("cmd") == "estop" or event_name == "estop":
            try:
                self._emit_telemetry_event("arduino_estop", msg)
            except Exception:
                pass
        if msg.get("telemetry") and msg.get("rfid"):
            self._record_rfid(msg.get("rfid"))

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
            try:
                requests.post(endpoint, json=body, timeout=0.5)
            except Exception:
                pass
        except Exception:
            pass
