from __future__ import annotations
import argparse
import logging
from threading import Event
import audioop
from typing import Optional, Callable, Iterable

from modules.speech.config_loader import load_config
from modules.speech.services.audio_capture import AudioCapture
from modules.speech.services.recognizer import Recognizer, RecognitionResult
from modules.speech.services.direction import DirectionEstimator
from modules.speech.services.pan_tilt import PanTiltController
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


class SpeechService:
    """High-level facade to run audio capture and speech recognition."""

    def __init__(self, config_path: Optional[str] = None):
        self.cfg = load_config(config_path)
        self._stop_event = Event()
        self.capture = AudioCapture(self.cfg.get("audio", {}))
        self.recognizer = Recognizer(self.cfg.get("recognition", {}))
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
        self._stop_event.clear()
        stream: Iterable[bytes] = self.capture.stream()
        for result in self.recognizer.run(self._direction_wrapper(stream)):
            if on_result:
                on_result(result)
            if self._stop_event.is_set():
                break

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
                    mono = audioop.tomono(chunk, 2, 1.0, 0.0)
                except Exception:
                    mono = chunk
                yield mono
            else:
                yield chunk

    def start_background(self, on_result: Optional[Callable[[RecognitionResult], None]] = None) -> None:
        import threading
        t = threading.Thread(target=self.start, kwargs={"on_result": on_result}, daemon=True)
        t.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.capture.stop()

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
            # Assuming gateway is at localhost:8080
            # We need to map 0-180 pan to whatever the arduino expects.
            # The arduino module expects "set_servo" with pan/tilt.
            # We only control pan here, tilt is kept at current or default?
            # Ideally we should know current tilt. For now let's send a specific command or just pan.
            # The arduino_serial module supports "set_servo" with optional args? 
            # Let's assume we send both, but we need to know tilt.
            # For now, let's just log if we can't send, but we try to send.
            
            # Better approach: The speech module shouldn't know about HTTP if possible, 
            # but since it's a service, it can talk to other services.
            
            url = "http://localhost:8080/arduino/send"
            # We default tilt to 90 if we don't know it. 
            # TODO: Get current tilt from state or keep track of it.
            payload = {"cmd": "set_servo", "pan": int(angle_deg), "tilt": 90} 
            requests.post(url, json=payload, timeout=0.1)
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
        uvicorn.run(create_app(args.config), host=host, port=port)
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
