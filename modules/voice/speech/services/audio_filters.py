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

try:
    import numpy as np
except Exception:
    np = None

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
        n = (len(chunk) // 8) * 2
        if n < 2:
            return b""
        if np is not None:
            arr = np.frombuffer(chunk[: n * 4], dtype="<i4")
            mixed = (arr[0::2] + arr[1::2]) // 2
            return np.clip(mixed >> 16, -32768, 32767).astype("<i2").tobytes()
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
    n = (len(chunk) // 4) * 2
    if n < 2:
        return b""
    if np is not None:
        arr = np.frombuffer(chunk[: n * 2], dtype="<i2")
        mixed = (arr[0::2].astype(np.int32) + arr[1::2].astype(np.int32)) // 2
        return mixed.astype("<i2").tobytes()
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
    g = float(gain)
    if np is not None:
        arr = np.frombuffer(chunk[: n * 2], dtype="<i2")
        scaled = (arr.astype(np.float64) * g).astype(np.int64)
        return np.clip(scaled, -32768, 32767).astype("<i2").tobytes()
    vals = struct.unpack("<" + "h" * n, chunk[: n * 2])
    out = []
    for v in vals:
        s = int(v * g)
        if s > 32767:
            s = 32767
        elif s < -32768:
            s = -32768
        out.append(s)
    return struct.pack("<" + "h" * len(out), *out)


class SoftwareEchoGate:
    """Software Acoustic Echo Suppression (AES) and Barge-In Gate.

    When robot TTS speaker output is playing, microphone input contains speaker echo.
    This filter suppresses microphone audio below the estimated speaker echo floor
    to prevent false wake-word or self-talk loops, while allowing intentional,
    louder human speech to cleanly break through for natural barge-in.
    """

    def __init__(
        self,
        suppression_gain: float = 0.12,
        barge_in_ratio: float = 2.2,
        hold_time_s: float = 0.25,
    ) -> None:
        self.suppression_gain = float(suppression_gain)
        self.barge_in_ratio = float(barge_in_ratio)
        self.hold_time_s = float(hold_time_s)
        self._tts_playing: bool = False
        self._last_tts_activity_ts: float = 0.0
        self._estimated_echo_rms: float = 1200.0

    def set_tts_playback(self, active: bool, estimated_rms: float = 1200.0) -> None:
        self._tts_playing = bool(active)
        if active:
            self._last_tts_activity_ts = time.time()
            self._estimated_echo_rms = max(300.0, float(estimated_rms))

    def is_echo_active(self, now: Optional[float] = None) -> bool:
        ts = now if now is not None else time.time()
        if self._tts_playing:
            return True
        return (ts - self._last_tts_activity_ts) < self.hold_time_s

    def process_chunk(self, chunk: bytes, input_rms: float) -> tuple[bytes, bool]:
        """Returns (processed_pcm, barge_in_triggered)."""
        now = time.time()
        if not self.is_echo_active(now):
            return chunk, False

        # If user speaks loudly over TTS, trigger barge-in and pass chunk through
        threshold = self._estimated_echo_rms * self.barge_in_ratio
        if input_rms >= threshold:
            return chunk, True

        # Otherwise attenuate chunk to suppress speaker echo
        suppressed = apply_gain_pcm16(chunk, self.suppression_gain)
        return suppressed, False


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
    _echo_gate: Optional[SoftwareEchoGate]

    def set_tts_playback_state(self, active: bool, estimated_rms: float = 1200.0) -> None:
        """Inform speech filter about TTS playback status for acoustic echo suppression."""
        if getattr(self, "_echo_gate", None) is None:
            self._echo_gate = SoftwareEchoGate()
        self._echo_gate.set_tts_playback(active, estimated_rms)

    def _on_barge_in_breakthrough(self) -> None:
        logger.info("Human barge-in speech breakthrough detected during TTS playback")

    def _append_utterance_pcm(self, mono: bytes) -> None:
        if not mono or not self._auto_language:
            return
        self._utterance_pcm.extend(mono)
        overflow = len(self._utterance_pcm) - self._max_utterance_bytes
        if overflow > 0:
            del self._utterance_pcm[:overflow]

    def clear_utterance_buffer(self) -> None:
        self._utterance_pcm.clear()

    def _get_capture_channels(self) -> int:
        cap = getattr(self, "capture", None)
        cfg = getattr(cap, "cfg", None)
        return int(getattr(cfg, "channels", 2))

    def _get_capture_dtype(self) -> str:
        cap = getattr(self, "capture", None)
        cfg = getattr(cap, "cfg", None)
        return str(getattr(cfg, "dtype", "int16"))

    def _compute_chunk_rms(self, chunk: bytes) -> float:
        if len(chunk) < 2:
            return 0.0
        count = len(chunk) // 2
        if not count:
            return 0.0
        step = 2 if self._get_capture_channels() >= 2 else 1
        if np is not None:
            arr = np.frombuffer(chunk[: count * 2], dtype="<i2")[0::step]
            if arr.size == 0:
                return 0.0
            return float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
        vals = struct.unpack("<" + "h" * count, chunk[: count * 2])
        acc = 0.0
        n = 0
        for i in range(0, len(vals), step):
            v = float(vals[i])
            acc += v * v
            n += 1
        return math.sqrt(acc / n) if n else 0.0

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
            rms = 0.0
            has_rms = False
            try:
                if len(chunk) >= 2 and (len(chunk) // 2) > 0:
                    rms = self._compute_chunk_rms(chunk)
                    has_rms = True
            except Exception:
                pass
            try:
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
                if has_rms:
                    self._last_audio_level = min(1.0, rms / 8000.0)
            except Exception:
                pass
            if self._get_capture_channels() >= 2:
                dtype = self._get_capture_dtype()
                try:
                    if audioop is not None:
                        mono = audioop.tomono(chunk, 2, 1.0, 0.0)
                    else:
                        mono = downmix_stereo_pcm(chunk, dtype)
                except Exception:
                    mono = downmix_stereo_pcm(chunk, dtype)
                mono = apply_gain_pcm16(mono, self._stt_input_gain)
                if getattr(self, "_echo_gate", None) is not None:
                    mono, barge_in = self._echo_gate.process_chunk(mono, rms)
                    if barge_in:
                        self._on_barge_in_breakthrough()
                self._append_utterance_pcm(mono)
                yield mono
            else:
                mono = apply_gain_pcm16(chunk, self._stt_input_gain)
                if getattr(self, "_echo_gate", None) is not None:
                    mono, barge_in = self._echo_gate.process_chunk(mono, rms)
                    if barge_in:
                        self._on_barge_in_breakthrough()
                self._append_utterance_pcm(mono)
                yield mono


__all__ = [
    "downmix_stereo_pcm",
    "apply_gain_pcm16",
    "SoftwareEchoGate",
    "SpeechAudioFilterMixin",
]
