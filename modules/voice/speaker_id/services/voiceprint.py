"""Voiceprint MVP: numpy-only acoustic profile + cosine matcher.

Modern upgrade path (Pi): swap `VoiceprintEmbedder` with an ONNX speaker
embedding model (e.g. ECAPA loaded via onnxruntime) -- the store/matcher API
does not change.
"""
from __future__ import annotations

import logging
import math
from typing import Any, List, Optional

import numpy as np

logger = logging.getLogger("voice.speaker_id.voiceprint")


def to_mono_f32(data: Any) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 2:                      # (N, ch) or (ch, N)
        if arr.shape[0] <= 2 and arr.shape[0] < arr.shape[1]:
            arr = arr.T
        arr = np.mean(arr, axis=-1, dtype=np.float32)
    return arr.ravel()


def pcm_b64_to_f32(b64: str) -> np.ndarray:
    import base64

    raw = base64.b64decode(str(b64 or ""))
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return data


def f32_to_pcm_b64(data: Any) -> str:
    import base64

    arr = np.clip(np.asarray(data, dtype=np.float32), -1.0, 1.0)
    return base64.b64encode((arr * 32767.0).astype(np.int16).tobytes()).decode("ascii")


class VoiceprintEmbedder:
    """Deterministic spectral+pitch embedding over voiced windows."""

    def __init__(self, bands: int = 20, window_s: float = 0.025, hop_s: float = 0.01,
                 min_energy_rms: float = 0.004) -> None:
        self.bands = max(8, int(bands))
        self.window = int(0.025 * 48000)     # fixed 24 kHz analysis SR
        self.hop = int(0.01 * 48000)
        self.analysis_sr = 24000
        self.min_energy_rms = float(min_energy_rms)
        self._filters = self._mel_filters(self.analysis_sr, 0, 7600, self.bands, 512)

    @staticmethod
    def _mel_filters(sr: int, fmin: float, fmax: float, n_bands: int, n_fft: int) -> np.ndarray:
        def hz_to_mel(f: float) -> float:
            return 2595.0 * math.log10(1.0 + f / 700.0)

        def mel_to_hz(m: float) -> float:
            return 700.0 * (10 ** (m / 2595.0) - 1.0)

        m0, m1 = hz_to_mel(fmin), hz_to_mel(fmax)
        pts = [mel_to_hz(m0 + (m1 - m0) * i / (n_bands + 1)) for i in range(n_bands + 2)]
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        fb = np.zeros((n_bands, len(freqs)), dtype=np.float32)
        for i in range(n_bands):
            lo, mid, hi = pts[i], pts[i + 1], pts[i + 2]
            up = (freqs - lo) / max(1e-9, mid - lo)
            down = (hi - freqs) / max(1e-9, hi - mid)
            fb[i] = np.clip(np.minimum(up, down), 0.0, None)
        norms = fb.sum(axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return fb / norms

    def _resample(self, data: np.ndarray, sr: int) -> np.ndarray:
        if sr == self.analysis_sr or data.size == 0:
            return data.astype(np.float32)
        new_size = max(1, int(round(data.size * (self.analysis_sr / float(sr)))))
        x_old = np.arange(data.size)
        x_new = np.linspace(0.0, data.size - 1, new_size)
        return np.interp(x_new, x_old, data).astype(np.float32)

    def embed(self, pcm: Any, samplerate: int) -> Optional[List[float]]:
        """Return the embedding vector, or None when the clip has too little speech."""
        arr = self._resample(to_mono_f32(pcm), int(samplerate or 0))
        if arr.size < self.window * 3:
            return None
        frames = max(1, (arr.size - self.window) // self.hop + 1)
        win = np.hanning(self.window).astype(np.float32)
        gates = []
        energies = []
        for i in range(frames):
            seg = arr[i * self.hop: i * self.hop + self.window]
            if seg.size < self.window:
                break
            rms = float(np.sqrt(np.mean(np.square(seg), dtype=np.float64)) + 1e-12)
            energies.append(rms)
            gates.append(rms)
        em = np.asarray(energies)
        gate = max(self.min_energy_rms, float(np.median(em) * 0.35))
        voiced_idx = [i for i, e in enumerate(energies) if e >= gate and e > self.min_energy_rms]
        if len(voiced_idx) < 3:
            return None
        band_means = []
        f0s = []
        for idx in [int(j) for j in voiced_idx]:
            offset = int(idx) * self.hop
            seg = arr[offset: offset + self.window] * win
            spec = np.abs(np.fft.rfft(seg, 512))
            mel = self._filters @ spec
            band_means.append(np.log(mel + 1e-8))
            f0 = self._pitch(seg)
            if f0 > 0:
                f0s.append(f0)
        means = np.mean(band_means, axis=0)
        stds = np.std(band_means, axis=0)
        f0_med = float(np.median(f0s)) if f0s else 0.0
        f0_spread = float(np.std(f0s)) if f0s else 0.0
        zcr = self._zcr(arr)
        vec = np.concatenate([
            means, stds,
            [(f0_med / 400.0) if f0_med else 0.0, (f0_spread / 150.0) if f0_spread else 0.0],
            [zcr],
        ]).astype(np.float32)
        n = float(np.linalg.norm(vec)) or 1.0
        return [round(float(x), 5) for x in (vec / n)]

    def _pitch(self, seg: np.ndarray) -> float:
        seg = seg - float(np.mean(seg))
        corr = np.correlate(seg, seg, mode="full")[seg.size - 1:]
        corr = corr / (float(np.max(corr)) or 1.0)
        lo, hi = int(self.analysis_sr / 400), int(self.analysis_sr / 60)
        if hi >= corr.size:
            hi = corr.size - 1
        if hi - lo < 4:
            return 0.0
        lag = int(np.argmax(corr[lo: hi])) + lo
        peak = float(corr[lag])
        if peak < 0.35:
            return 0.0
        return self.analysis_sr / lag

    @staticmethod
    def _zcr(data: np.ndarray) -> float:
        if data.size < 2:
            return 0.0
        sign = np.signbit(data)
        return float(np.mean(sign[1:] != sign[:-1]))
