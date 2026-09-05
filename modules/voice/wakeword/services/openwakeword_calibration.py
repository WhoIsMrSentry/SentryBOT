from __future__ import annotations

from collections import deque
import logging
import time
from typing import Any, Dict, Optional

try:
    import numpy as np
except Exception:
    np = None

from .openwakeword_assets import _score_value

logger = logging.getLogger("wakeword.openwakeword_calibration")


class OpenWakewordCalibrationMixin:
    """PCM audio normalization, score smoothing, and noise calibration."""

    _input_channels: int
    _input_gain: float
    _smooth_window: int
    _score_history: Dict[str, deque]
    _auto_calibration_enabled: bool
    _calibration_done: bool
    _calibration_scores: list[float]
    _calibration_started_ts: float
    _calibration_duration_sec: float
    _calibration_min_samples: int
    _calibration_percentile: float
    _calibration_margin: float
    _calibration_min_threshold: float
    _calibration_max_threshold: float
    _threshold: float
    _log_every_n_chunks: int
    _chunk_counter: int
    _verifier: Any
    _model: Any

    def _parse_audio(self, chunk: bytes) -> Optional[np.ndarray]:
        if np is None:
            return None
        audio = None
        try:
            audio16 = np.frombuffer(chunk, dtype=np.int16)
            if audio16.size > 0:
                audio = audio16
        except Exception:
            audio = None
        if audio is None or audio.size == 0:
            if len(chunk) % 4 == 0:
                try:
                    audio32 = np.frombuffer(chunk, dtype=np.int32)
                    audio = (audio32 >> 16).astype(np.int16)
                except Exception:
                    audio = None
        if audio is None or audio.size == 0:
            try:
                audio = np.frombuffer(chunk, dtype=np.int16)
            except Exception:
                logger.debug("openwakeword: failed to interpret audio chunk bytes")
                return None
        if self._input_channels >= 2 and audio.size >= 2:
            ch0 = audio[0::self._input_channels].astype(np.int32)
            ch1 = audio[1::self._input_channels].astype(np.int32)
            audio = ((ch0 + ch1) // 2).astype(np.int16) if ch1.size else ch0.astype(np.int16)
        if self._input_gain != 1.0 and audio.size:
            boosted = audio.astype(np.float32) * float(self._input_gain)
            audio = np.clip(boosted, -32768.0, 32767.0).astype(np.int16)
        return audio

    def _smooth_scores(self, scores: dict) -> tuple[Optional[str], float]:
        best_label: Optional[str] = None
        best_score = 0.0
        for name, value in scores.items():
            score = _score_value(value)
            if score is None:
                continue
            history = self._score_history.setdefault(name, deque(maxlen=max(1, self._smooth_window)))
            history.append(score)
            smoothed = sum(history) / len(history)
            if smoothed > best_score:
                best_score = smoothed
                best_label = name
        return best_label, best_score

    def _run_auto_calibration(self, best_score: float) -> bool:
        if not self._auto_calibration_enabled or self._calibration_done:
            return True
        self._calibration_scores.append(float(best_score))
        elapsed = time.time() - self._calibration_started_ts
        enough_time = elapsed >= self._calibration_duration_sec
        enough_samples = len(self._calibration_scores) >= self._calibration_min_samples
        if not (enough_time and enough_samples):
            return False
        try:
            noise_p = float(np.percentile(np.asarray(self._calibration_scores, dtype=np.float32), self._calibration_percentile))
        except Exception:
            noise_p = max(self._calibration_scores) if self._calibration_scores else 0.0
        calibrated = noise_p + self._calibration_margin
        calibrated = max(self._calibration_min_threshold, min(self._calibration_max_threshold, calibrated))
        old_threshold = self._threshold
        self._threshold = float(calibrated)
        self._calibration_done = True
        logger.info(
            "openwakeword auto-calibration done: samples=%d elapsed=%.1fs noise_p=%.6f threshold %.6f -> %.6f",
            len(self._calibration_scores), elapsed, noise_p, old_threshold, self._threshold,
        )
        return True

    def _log_periodic_probe(self, best_label: Optional[str], best_score: float):
        if not self._log_every_n_chunks or (self._chunk_counter % self._log_every_n_chunks != 0):
            return
        if self._auto_calibration_enabled and not self._calibration_done:
            logger.info(
                "openwakeword probe(calibrating): best=%s score=%.4f threshold=%.4f samples=%d",
                best_label, best_score, self._threshold, len(self._calibration_scores),
            )
        else:
            logger.debug("openwakeword probe: best=%s score=%.4f threshold=%.4f", best_label, best_score, self._threshold)

    def _verify_label(self, label: str) -> bool:
        if self._verifier is None:
            return True
        try:
            feats = self._model.preprocessor.get_features(self._model.model_inputs.get(label))
            return bool(self._verifier.predict([feats.flatten()])[0])
        except Exception:
            return True
