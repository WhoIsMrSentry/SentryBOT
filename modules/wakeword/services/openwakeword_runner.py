from __future__ import annotations
import logging
import time
from collections import deque
import importlib
from pathlib import Path
from typing import Dict, Iterable, Optional

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

try:
    from openwakeword.model import Model as OpenWakeWordModel  # type: ignore
except Exception:
    OpenWakeWordModel = None  # type: ignore

logger = logging.getLogger("wakeword.openwakeword")
# Reduce noisy debug output by default; change to DEBUG when troubleshooting explicitly.
try:
    logger.setLevel(logging.INFO)
except Exception:
    pass


def _as_float(value) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _score_value(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return _as_float(value[-1])
    try:
        import numpy as _np  # type: ignore

        if isinstance(value, _np.ndarray):
            if value.size == 0:
                return None
            return _as_float(value.reshape(-1)[-1])
    except Exception:
        pass
    return _as_float(value)


def _resolve_pretrained_models(model_names: list, inference_framework: str = "onnx") -> Dict[str, str]:
    """Resolve built-in openWakeWord models (e.g. hey_mycroft) and ensure they are downloaded."""
    try:
        import openwakeword  # type: ignore
        from openwakeword.utils import download_models  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"openwakeword is required for pretrained models: {exc}") from exc

    catalog = getattr(openwakeword, "MODELS", {}) or {}
    if not catalog:
        raise RuntimeError("openwakeword.MODELS catalog is empty")

    normalized: list[str] = []
    for raw in model_names:
        key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
        if not key:
            continue
        if key not in catalog:
            aliases = {name.replace("_", ""): name for name in catalog}
            compact = key.replace("_", "")
            if compact in aliases:
                key = aliases[compact]
            else:
                raise ValueError(f"unknown openwakeword pretrained model: {raw}")
        normalized.append(key)

    if not normalized:
        raise ValueError("pretrained_models is empty")

    download_models(model_names=normalized)
    use_onnx = str(inference_framework or "onnx").strip().lower() == "onnx"
    resolved: Dict[str, str] = {}
    for key in normalized:
        base_path = Path(str(catalog[key]["model_path"]))
        candidate = base_path.with_suffix(".onnx" if use_onnx else ".tflite")
        if not candidate.exists() and base_path.exists():
            candidate = base_path
        if not candidate.exists():
            raise FileNotFoundError(f"openwakeword model missing after download: {candidate}")
        resolved[key] = str(candidate.resolve())
    return resolved


def _resolve_model_paths(model_paths) -> Dict[str, str]:
    module_root = Path(__file__).resolve().parents[1]

    def _abs_path(path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = (module_root / p).resolve()
        return str(p)

    resolved: Dict[str, str] = {}
    if isinstance(model_paths, dict):
        for label, path in model_paths.items():
            if isinstance(path, str) and path:
                resolved[str(label)] = _abs_path(path)
        return resolved
    if isinstance(model_paths, list):
        for path in model_paths:
            if isinstance(path, str) and path:
                abs_path = _abs_path(path)
                label = Path(abs_path).stem
                resolved[label] = abs_path
        return resolved
    if isinstance(model_paths, str) and model_paths:
        abs_path = _abs_path(model_paths)
        resolved[Path(abs_path).stem] = abs_path
    return resolved


class OpenWakewordRunner:
    def __init__(self, cfg: dict):
        if OpenWakeWordModel is None or np is None:
            raise RuntimeError("openwakeword and numpy are required for openwakeword engine")
        # openwakeword package resources preflight (some wheels/environments miss these files)
        try:
            ow_pkg = importlib.import_module("openwakeword")
            pkg_dir = Path(getattr(ow_pkg, "__file__", "")).resolve().parent
            required = pkg_dir / "resources" / "models" / "melspectrogram.onnx"
            if not required.exists():
                raise RuntimeError(
                    f"openwakeword runtime resource missing: {required}. "
                    "Reinstall openwakeword or use wakeword.engine=vosk."
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
        if isinstance(pretrained, list) and pretrained:
            model_paths = _resolve_pretrained_models(pretrained, inference_framework)
        else:
            model_paths = _resolve_model_paths(cfg.get("model_paths"))
        if not model_paths:
            raise ValueError("openwakeword.pretrained_models or openwakeword.model_paths is required")
        self._labels = list(model_paths.keys())
        # Instantiate model in a backward/forward-compatible way.
        # Prefer kwargs so inference_framework maps correctly even when
        # upstream uses a permissive (*args, **kwargs) constructor.
        paths_list = list(model_paths.values())
        model_ctor = OpenWakeWordModel

        def _try_ctor(kwargs=None, args=None):
            kwargs = kwargs or {}
            args = args or []
            try:
                return model_ctor(*args, **kwargs)
            except TypeError as e:
                # Pass the TypeError up for outer handling/logging
                raise

        # Preferred: explicit wakeword_models + inference_framework
        tried = []
        last_exc = None
        candidates = [
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
            # All attempts failed — surface a helpful error message
            logger.debug("openwakeword ctor attempts: %s", tried)
            raise RuntimeError(f"openwakeword model instantiation failed: {last_exc}")
        self._threshold = float(cfg.get("threshold", 0.5))
        self._smooth_window = int(cfg.get("smooth_window", 3))
        self._input_channels = max(1, int(cfg.get("input_channels", 1)))
        self._input_gain = float(cfg.get("input_gain", 1.0))
        self._log_every_n_chunks = max(0, int(cfg.get("log_every_n_chunks", 200)))
        self._chunk_counter = 0
        # Automatic threshold calibration using startup ambient noise profile.
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
        # optional verifier
        self._verifier = None
        verifier_path = cfg.get("verifier_path")
        if verifier_path:
            try:
                import pickle
                p = Path(verifier_path)
                if not p.exists():
                    # try relative to module
                    p = Path(__file__).resolve().parents[1] / verifier_path
                if p.exists():
                    with open(p, "rb") as f:
                        self._verifier = pickle.load(f)
            except Exception:
                logger.debug("failed to load verifier: %s", verifier_path)

    def run(self, stream: Iterable[bytes]) -> Iterable[str]:
        for chunk in stream:
            label = self._infer_chunk(chunk)
            if label:
                yield label

    def _parse_audio(self, chunk: bytes) -> Optional[np.ndarray]:
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
