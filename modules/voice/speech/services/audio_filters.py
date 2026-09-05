from __future__ import annotations

import logging
import math
import struct
import time
from typing import Any, Dict, Optional

try:
    import audioop
except Exception:
    audioop = None

logger = logging.getLogger("speech.audio_filters")


def downmix_stereo_pcm(chunk: bytes, dtype: str = "int16") -> bytes:
    """Downmix interleaved stereo PCM to mono without requiring audioop.

    Supports int16 and a best-effort int32->int16 conversion.
    """
    if not chunk:
        return chunk
    dt = (dtype or "int16").lower()
    if dt == "int32":
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


def apply_gain_pcm16(chunk: bytes, gain: float) -> bytes:
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


class SpeechAudioFilterMixin:
    """PCM gain, direction estimation wrapper, VU-meter RMS, and stereo downmix."""

    cfg: Dict[str, Any]
    capture: Any
    _direction: Any
    _last_angle: Optional[float]
    _last_audio_level: float
    _tracking: bool
    _pan: Any
    _stt_input_gain: float
    _auto_language: bool
    _utterance_pcm: bytearray
    _max_utterance_bytes: int

    def _append_utterance_pcm(self, mono: bytes) -> None:
        if not mono or not self._auto_language:
            return
        self._utterance_pcm.extend(mono)
        overflow = len(self._utterance_pcm) - self._max_utterance_bytes
        if overflow > 0:
            del self._utterance_pcm[:overflow]

    def clear_utterance_buffer(self) -> None:
        self._utterance_pcm.clear()

    def _direction_wrapper(self, stream):
        if not self._direction:
            yield from stream
            return
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
                rms = 0.0
                if len(chunk) >= 2:
                    count = len(chunk) // 2
                    if count:
                        vals = struct.unpack("<" + "h" * count, chunk[: count * 2])
                        step = 2 if self.capture.cfg.channels >= 2 else 1
                        acc = 0.0
                        n = 0
                        for i in range(0, len(vals), step):
                            acc += (vals[i]) * (vals[i])
                            n += 1
                        if n:
                            rms = math.sqrt(acc / n)

                if energy_th and rms < energy_th:
                    pass
                else:
                    angle = self._direction.estimate(chunk)
                    if invert:
                        angle = -angle
                    if last_out is not None and abs(angle - last_out) < deadband:
                        angle = last_out
                    if last_out is not None and 0.0 < alpha < 1.0:
                        angle = alpha * angle + (1 - alpha) * last_out
                    now = time.time()
                    if last_out is not None and last_ts is not None and slew > 0:
                        dt = max(1e-3, now - last_ts)
                        max_step = slew * dt
                        if abs(angle - last_out) > max_step:
                            angle = last_out + (max_step if angle > last_out else -max_step)
                    self._last_angle = angle
                    if self._tracking:
                        center = float(self.cfg.get("pan_tilt", {}).get("center_deg", 90.0))
                        target = center + angle
                        self._pan.set_target(target)
                    last_out = angle
                    last_ts = time.time()
            except Exception:
                pass
            try:
                if len(chunk) >= 2:
                    count = len(chunk) // 2
                    vals = struct.unpack("<" + "h" * count, chunk[: count * 2])
                    step = 2 if self.capture.cfg.channels >= 2 else 1
                    acc = 0.0
                    n = 0
                    for i in range(0, len(vals), step):
                        acc += float(vals[i]) * float(vals[i])
                        n += 1
                    if n:
                        rms = (acc / n) ** 0.5
                        self._last_audio_level = min(1.0, rms / 8000.0)
            except Exception:
                pass
            if self.capture.cfg.channels >= 2:
                try:
                    if audioop is not None:
                        mono = audioop.tomono(chunk, 2, 1.0, 0.0)
                    else:
                        mono = downmix_stereo_pcm(chunk, self.capture.cfg.dtype)
                except Exception:
                    mono = downmix_stereo_pcm(chunk, self.capture.cfg.dtype)
                mono = apply_gain_pcm16(mono, self._stt_input_gain)
                self._append_utterance_pcm(mono)
                yield mono
            else:
                mono = apply_gain_pcm16(chunk, self._stt_input_gain)
                self._append_utterance_pcm(mono)
                yield mono
