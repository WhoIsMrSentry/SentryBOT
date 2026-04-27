from __future__ import annotations
import argparse
import logging
import struct
from threading import Event, Lock
try:
    import audioop
except Exception:
    audioop = None
    # Don't fail import; we'll degrade direction/downmix functionality and log at runtime.
from typing import Optional, Callable, Iterable

from modules.speech.config_loader import load_config
from modules.speech.services.audio_capture import AudioCapture, get_shared_capture, release_shared_capture
from modules.speech.services.recognizer import Recognizer, RecognitionResult
from modules.speech.services.direction import DirectionEstimator
from modules.speech.services.pan_tilt import PanTiltController
from modules.arduino_serial.contract import build_set_servo_cmd, SERVO_INDEX_PAN
from fastapi import FastAPI
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.speech.api import get_router  # type: ignore

try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass

logger = logging.getLogger("speech")


def _downmix_stereo_pcm(chunk: bytes, dtype: str = "int16") -> bytes:
    """Downmix interleaved stereo PCM to mono without requiring audioop.

    Supports int16 and a best-effort int32->int16 conversion.
    """
    if not chunk:
        return chunk
    dt = (dtype or "int16").lower()
    if dt == "int32":
        # int32 interleaved stereo -> mix -> int16
        if len(chunk) < 8:
            return b""
        n = len(chunk) // 4
        vals = struct.unpack("<" + "i" * n, chunk[: n * 4])
        mono = []
        for i in range(0, len(vals) - 1, 2):
            mixed = (vals[i] + vals[i + 1]) // 2
            mono.append(int(max(-32768, min(32767, mixed >> 16))))
        if not mono:
            return b""
        return struct.pack("<" + "h" * len(mono), *mono)

    # Default: int16
    if len(chunk) < 4:
        return b""
    n = len(chunk) // 2
    vals = struct.unpack("<" + "h" * n, chunk[: n * 2])
    mono = []
    for i in range(0, len(vals) - 1, 2):
        mono.append((int(vals[i]) + int(vals[i + 1])) // 2)
    if not mono:
        return b""
    return struct.pack("<" + "h" * len(mono), *mono)


def _apply_gain_pcm16(chunk: bytes, gain: float) -> bytes:
    if not chunk or gain == 1.0:
        return chunk
    if len(chunk) < 2:
        return chunk
    n = len(chunk) // 2
    vals = struct.unpack("<" + "h" * n, chunk[: n * 2])
    out = []
    g = float(gain)
    for v in vals:
        s = int(v * g)
        if s > 32767:
            s = 32767
        elif s < -32768:
            s = -32768
        out.append(s)
    return struct.pack("<" + "h" * len(out), *out)


class SpeechService:
    """High-level facade to run audio capture and speech recognition."""

    def __init__(self, config_path: Optional[str] = None):
        self.cfg = load_config(config_path)
        self._stop_event = Event()
        self._listening = False
        self._listen_lock = Lock()
        self._result_lock = Lock()
        self._on_result_cb: Optional[Callable[[RecognitionResult], None]] = None
        self._thread = None
        self.capture = get_shared_capture(self.cfg.get("audio", {}))
        self.recognizer = Recognizer(self.cfg.get("recognition", {}))
        rec_cfg = self.cfg.get("recognition", {}) or {}
        self.source_language = str(rec_cfg.get("source_language") or rec_cfg.get("language") or "tr")
        self._stt_input_gain = float(rec_cfg.get("input_gain", 1.0))
        # Direction estimator (optional, needs stereo)
        dir_cfg = self.cfg.get("direction", {})
        self.direction_enabled = bool(dir_cfg.get("enabled", False)) and self.capture.cfg.channels >= 2
        self._direction = DirectionEstimator(self.capture.cfg.samplerate) if self.direction_enabled else None
        self._last_angle = None
        # Pan-tilt controller (optional)
        pt_cfg = self.cfg.get("pan_tilt", {})
        self._pan = PanTiltController(pt_cfg, sender=self._send_pan)
        self._tracking = False

    def start(self, on_result: Optional[Callable[[RecognitionResult], None]] = None) -> None:
        """Start capturing and recognition in the same thread using a generator pipeline.

        For production, consider running capture in its own thread and feeding a queue.
        """
        with self._listen_lock:
            if self._listening:
                return
            self._listening = True
        if on_result is not None:
            with self._result_lock:
                self._on_result_cb = on_result
        self._stop_event.clear()
        try:
            stream: Iterable[bytes] = self.capture.stream()
            for result in self.recognizer.run(self._direction_wrapper(stream)):
                cb = None
                with self._result_lock:
                    cb = self._on_result_cb
                if cb:
                    cb(result)
                if self._stop_event.is_set():
                    break
        except Exception as exc:
            logger.warning("speech degraded: recognizer stopped (%s)", exc)
        finally:
            with self._listen_lock:
                self._listening = False

    def _direction_wrapper(self, stream):
        if not self._direction:
            yield from stream
            return
        # Control parameters
        ctrl = (self.cfg.get("direction", {}) or {}).get("control", {})
        invert = bool(ctrl.get("invert_direction", False))
        deadband = float(ctrl.get("deadband_deg", 0.0))
        alpha = float(ctrl.get("smoothing_alpha", 0.0))
        slew = float(ctrl.get("slew_deg_per_s", 0.0))
        energy_th = float(ctrl.get("energy_threshold", 0.0))
        last_out = None
        last_ts = None
        for chunk in stream:
            try:
                # Energy gate (RMS)
                import math, time
                # 16-bit PCM
                rms = 0.0
                if len(chunk) >= 2:
                    import struct
                    count = len(chunk) // 2
                    if count:
                        vals = struct.unpack('<' + 'h'*count, chunk[:count*2])
                        # use mono mix for energy
                        step = 2 if self.capture.cfg.channels >= 2 else 1
                        acc = 0.0
                        n = 0
                        for i in range(0, len(vals), step):
                            acc += (vals[i])*(vals[i])
                            n += 1
                        if n:
                            rms = math.sqrt(acc / n)

                if energy_th and rms < energy_th:
                    # energy too low; don't update angle
                    pass
                else:
                    angle = self._direction.estimate(chunk)
                    if invert:
                        angle = -angle
                    # deadband vs last_out
                    if last_out is not None and abs(angle - last_out) < deadband:
                        angle = last_out
                    # smoothing
                    if last_out is not None and 0.0 < alpha < 1.0:
                        angle = alpha * angle + (1 - alpha) * last_out
                    # slew-rate limit
                    now = time.time()
                    if last_out is not None and last_ts is not None and slew > 0:
                        dt = max(1e-3, now - last_ts)
                        max_step = slew * dt
                        if abs(angle - last_out) > max_step:
                            angle = last_out + (max_step if angle > last_out else -max_step)
                    self._last_angle = angle
                    # if tracking, map to absolute pan angle
                    if self._tracking:
                        center = float(self.cfg.get("pan_tilt", {}).get("center_deg", 90.0))
                        target = center + angle
                        self._pan.set_target(target)
                    last_out = angle
                    last_ts = time.time()
            except Exception:
                pass
            # Downmix to mono for recognizer if input is stereo
            if self.capture.cfg.channels >= 2:
                try:
                    if audioop is not None:
                        mono = audioop.tomono(chunk, 2, 1.0, 0.0)
                    else:
                        mono = _downmix_stereo_pcm(chunk, self.capture.cfg.dtype)
                except Exception:
                    mono = _downmix_stereo_pcm(chunk, self.capture.cfg.dtype)
                mono = _apply_gain_pcm16(mono, self._stt_input_gain)
                yield mono
            else:
                yield _apply_gain_pcm16(chunk, self._stt_input_gain)

    def start_background(self, on_result: Optional[Callable[[RecognitionResult], None]] = None) -> None:
        import threading
        if on_result is not None:
            with self._result_lock:
                self._on_result_cb = on_result
        with self._listen_lock:
            if self._listening:
                return
        t = threading.Thread(target=self.start, kwargs={"on_result": None}, daemon=True)
        self._thread = t
        t.start()

    def stop(self) -> None:
        self._stop_event.set()
        release_shared_capture(self.capture)
        with self._listen_lock:
            self._listening = False

    def listen_once(self, timeout_sec: float = 5.0) -> Optional[RecognitionResult]:
        """Listen until first final result or timeout."""
        res: Optional[RecognitionResult] = None
        def _cb(r: RecognitionResult):
            nonlocal res
            if r.is_final and not res:
                res = r
                self.stop()
        self.start_background(on_result=_cb)
        self._stop_event.wait(timeout=timeout_sec)
        return res

    @property
    def last_angle(self) -> float | None:
        return self._last_angle

    @property
    def listening(self) -> bool:
        with self._listen_lock:
            return self._listening

    # Pan-tilt controls
    def track_start(self) -> None:
        self._tracking = True
        self._pan.start()

    def track_stop(self) -> None:
        self._tracking = False
        self._pan.stop()

    def track_status(self):
        st = self._pan.status()
        st["tracking"] = self._tracking
        st["angle"] = self._last_angle
        return st

    # Hardware send stub: replace with Arduino/driver integration
    def _send_pan(self, angle_deg: float) -> None:
        # Send to Arduino via HTTP (Gateway)
        # We use a simple requests call here, but in production consider async client or keeping a session
        try:
            import requests
            # Use request endpoint to get ACK/error for motion commands.
            url = "http://localhost:8080/arduino/request"
            payload = build_set_servo_cmd(SERVO_INDEX_PAN, int(angle_deg))
            requests.post(url, json=payload, params={"timeout": 0.1}, timeout=0.2)
        except Exception as e:
            logger.debug(f"Failed to send pan: {e}")


def create_app(config_path: str | None = None) -> FastAPI:
    """FastAPI app factory for the speech module."""
    service = SpeechService(config_path)
    app = FastAPI()
    from modules.speech.api import get_router  # local import to avoid circular
    app.include_router(get_router(service))
    return app


# CLI Entrypoint
def main():
    parser = argparse.ArgumentParser(description="Speech input service")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yml")
    parser.add_argument("--listen-once", action="store_true", help="Listen once and print the result")
    parser.add_argument("--api", action="store_true", help="Run FastAPI server using config server.host/port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.api:
        # Lazy import to avoid uvicorn dependency when not used
        import uvicorn  # type: ignore
        cfg = load_config(args.config)
        host = str(cfg.get("server", {}).get("host", "0.0.0.0"))
        port = int(cfg.get("server", {}).get("port", 8082))
        uvicorn.run(create_app(args.config), host=host, port=port, log_config=None)
        return

    service = SpeechService(args.config)
    if args.listen_once:
        result = service.listen_once()
        print(result)
    else:
        def printer(r: RecognitionResult):
            logger.info("%s", r)
        service.start(on_result=printer)


if __name__ == "__main__":
    main()
