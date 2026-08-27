from __future__ import annotations

# sentrybot_batch06e_no_hardware_wakeword_asset_guard
def _sentrybot_batch06e_skip_wakeword_assets():
    import os as _os
    return (
        str(_os.getenv("SENTRYBOT_NO_HARDWARE", "")).lower() in {"1", "true", "yes", "on"}
        or str(_os.getenv("SENTRYBOT_SKIP_WAKEWORD_AUTOSTART", "")).lower() in {"1", "true", "yes", "on"}
    )


from collections import deque
import os
import importlib
import logging
from pathlib import Path
import time
from typing import Dict, Iterable, Optional

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

try:
    from openwakeword.model import Model as OpenWakeWordModel  # type: ignore
except Exception:
    OpenWakeWordModel = None  # type: ignore

from .openwakeword_assets import (
    BUILTIN_FEATURE_MODELS_ONNX,
    BUILTIN_FEATURE_MODELS_TFLITE,
    BUILTIN_VAD_MODELS,
    BUILTIN_WAKE_MODELS,
    BUILTIN_WAKE_MODELS_ONNX,
    BUILTIN_WAKE_MODELS_TFLITE,
    _as_float,
    _score_value,
    _module_models_dir,
    _builtin_wake_models,
    _openwakeword_catalog,
    _feature_model_groups,
    _openwakeword_pkg_dir,
    _openwakeword_models_dir,
    _download_url,
    _framework_asset_url,
    _download_framework_asset,
    _try_utils_download_models,
    _ensure_openwakeword_assets,
    _normalize_pretrained_names,
    _resolve_pretrained_models,
    _resolve_model_paths,
)
from .openwakeword_calibration import OpenWakewordCalibrationMixin

logger = logging.getLogger("wakeword.openwakeword")
try:
    logger.setLevel(logging.INFO)
except Exception:
    pass


class OpenWakewordRunner(OpenWakewordCalibrationMixin):
    def __init__(self, cfg: dict):
        if OpenWakeWordModel is None or np is None:
            raise RuntimeError("openwakeword and numpy are required for openwakeword engine")
        try:
            ow_pkg = importlib.import_module("openwakeword")
            pkg_dir = Path(getattr(ow_pkg, "__file__", "")).resolve().parent
            _ensure_openwakeword_assets([], True)
            mel_candidates = [
                pkg_dir / "resources" / "models" / "melspectrogram.onnx",
                _module_models_dir() / "melspectrogram.onnx",
            ]
            if not any(path.exists() for path in mel_candidates):
                raise RuntimeError(
                    "openwakeword runtime resource missing: melspectrogram.onnx. "
                    "Please reinstall openwakeword."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"openwakeword preflight failed: {exc}")
        inference_framework = str(cfg.get("inference_framework", "onnx")).strip().lower() or "onnx"
        pretrained = cfg.get("pretrained_models")
        if pretrained is None:
            pretrained = cfg.get("pretrained_model")
        if isinstance(pretrained, str) and pretrained.strip():
            pretrained = [pretrained.strip()]
        pretrained_names: list[str] = []
        if isinstance(pretrained, list) and pretrained:
            model_paths, pretrained_names = _resolve_pretrained_models(pretrained, inference_framework)
        else:
            model_paths = _resolve_model_paths(cfg.get("model_paths"))
        if not model_paths:
            raise ValueError("openwakeword.pretrained_models or openwakeword.model_paths is required")
        self._labels = list(model_paths.keys())
        paths_list = list(model_paths.values())
        model_ctor = OpenWakeWordModel

        def _try_ctor(kwargs=None, args=None):
            kwargs = kwargs or {}
            args = args or []
            return model_ctor(*args, **kwargs)

        tried = []
        last_exc = None
        candidates = [
            {'kwargs': {'wakeword_models': pretrained_names or paths_list, 'inference_framework': inference_framework}},
            {'kwargs': {'wakeword_models': paths_list, 'inference_framework': inference_framework}},
            {'kwargs': {'model_paths': paths_list, 'inference_framework': inference_framework}},
            {'kwargs': {'models': paths_list, 'inference_framework': inference_framework}},
            {'kwargs': {'wakeword_models': paths_list}},
            {'args': [paths_list]},
        ]

        for cand in candidates:
            try:
                if 'kwargs' in cand:
                    self._model = _try_ctor(kwargs=cand['kwargs'])
                else:
                    self._model = _try_ctor(args=cand.get('args'))
                logger.info("openwakeword model instantiated using candidate: %s", list(cand.keys()))
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                tried.append((cand, str(exc)))

        if last_exc is not None:
            logger.debug("openwakeword ctor attempts: %s", tried)
            raise RuntimeError(f"openwakeword model instantiation failed: {last_exc}")
        self._threshold = float(cfg.get("threshold", 0.5))
        self._smooth_window = int(cfg.get("smooth_window", 3))
        self._input_channels = max(1, int(cfg.get("input_channels", 1)))
        self._input_gain = float(cfg.get("input_gain", 1.0))
        self._log_every_n_chunks = max(0, int(cfg.get("log_every_n_chunks", 200)))
        self._chunk_counter = 0

        cal_cfg = cfg.get("auto_calibration", {}) or {}
        self._auto_calibration_enabled = bool(cal_cfg.get("enabled", True))
        self._calibration_duration_sec = float(cal_cfg.get("duration_sec", 12.0))
        self._calibration_min_samples = max(20, int(cal_cfg.get("min_samples", 120)))
        self._calibration_percentile = float(cal_cfg.get("percentile", 99.5))
        self._calibration_margin = float(cal_cfg.get("margin", 0.0007))
        self._calibration_min_threshold = float(cal_cfg.get("min_threshold", 0.0012))
        self._calibration_max_threshold = float(cal_cfg.get("max_threshold", self._threshold))
        self._calibration_started_ts = time.time()
        self._calibration_scores: list[float] = []
        self._calibration_done = not self._auto_calibration_enabled
        self._score_history: Dict[str, deque] = {}
        if self._auto_calibration_enabled:
            logger.info(
                "openwakeword auto-calibration enabled: duration=%.1fs min_samples=%d pctl=%.2f margin=%.6f",
                self._calibration_duration_sec,
                self._calibration_min_samples,
                self._calibration_percentile,
                self._calibration_margin,
            )

        self._verifier = None
        verifier_path = cfg.get("verifier_path")
        if verifier_path:
            try:
                import pickle
                p = Path(verifier_path)
                if not p.exists():
                    p = Path(__file__).resolve().parents[1] / verifier_path
                if p.exists():
                    allow_pickle = str(os.getenv("SENTRYBOT_ALLOW_PICKLE_VERIFIER", "0")).strip().lower() in {"1", "true", "yes", "on"}
                    if not allow_pickle:
                        logger.warning("openwakeword verifier pickle skipped; set SENTRYBOT_ALLOW_PICKLE_VERIFIER=1 only for trusted local verifier files")
                    else:
                        with open(p, "rb") as f:
                            self._verifier = pickle.load(f)
            except Exception:
                logger.debug("failed to load verifier: %s", verifier_path)

    def run(self, stream: Iterable[bytes]) -> Iterable[str]:
        for chunk in stream:
            label = self._infer_chunk(chunk)
            if label:
                yield label

    def _infer_chunk(self, chunk: bytes) -> Optional[str]:
        if not chunk:
            return None
        self._chunk_counter += 1

        audio = self._parse_audio(chunk)
        if audio is None or audio.size == 0:
            return None

        try:
            scores = self._model.predict(audio)
        except Exception as exc:
            logger.debug("openwakeword inference failed: %s", exc)
            return None

        if not isinstance(scores, dict):
            logger.debug("openwakeword: predict did not return dict, got: %s", type(scores))
            return None

        best_label, best_score = self._smooth_scores(scores)
        logger.debug("openwakeword smoothed best=%s score=%s threshold=%s", best_label, best_score, self._threshold)

        if not self._run_auto_calibration(best_score):
            return None

        self._log_periodic_probe(best_label, best_score)

        if best_label and best_score >= self._threshold and self._verify_label(best_label):
            logger.info("openwakeword accepted: %s (score=%s)", best_label, best_score)
            return best_label
        return None
