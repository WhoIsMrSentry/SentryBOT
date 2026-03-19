from __future__ import annotations
import logging
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
        model_paths = _resolve_model_paths(cfg.get("model_paths"))
        if not model_paths:
            raise ValueError("openwakeword.model_paths is required")
        self._labels = list(model_paths.keys())
        inference_framework = str(cfg.get("inference_framework", "onnx")).strip().lower() or "onnx"
        try:
            self._model = OpenWakeWordModel(
                wakeword_models=list(model_paths.values()),
                inference_framework=inference_framework,
            )
        except TypeError:
            self._model = OpenWakeWordModel(wakeword_models=list(model_paths.values()))
        self._threshold = float(cfg.get("threshold", 0.5))
        self._smooth_window = int(cfg.get("smooth_window", 3))
        self._score_history: Dict[str, deque] = {}
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

    def _infer_chunk(self, chunk: bytes) -> Optional[str]:
        if not chunk:
            return None
        try:
            # Robustly handle different PCM widths and interleaved stereo.
            # Prefer int16, but fall back to int32 and downscale if needed.
            audio = None
            # try int16 view
            try:
                audio16 = np.frombuffer(chunk, dtype=np.int16)
                if audio16.size > 0:
                    audio = audio16
            except Exception:
                audio = None
            # fallback to int32 -> convert to int16
            if audio is None or audio.size == 0:
                if len(chunk) % 4 == 0:
                    try:
                        audio32 = np.frombuffer(chunk, dtype=np.int32)
                        # convert by shifting to 16-bit range
                        audio = (audio32 >> 16).astype(np.int16)
                    except Exception:
                        audio = None
            if audio is None or audio.size == 0:
                # last resort: try int16 again (best-effort)
                try:
                    audio = np.frombuffer(chunk, dtype=np.int16)
                except Exception:
                    logger.debug("openwakeword: failed to interpret audio chunk bytes")
                    return None
            # If interleaved stereo (even-length array), try to detect and downmix to mono
            if audio.size >= 2:
                # heuristics: compare energy of even and odd samples
                ch0 = audio[0::2].astype(np.int32)
                ch1 = audio[1::2].astype(np.int32)
                e0 = float(np.mean(np.abs(ch0))) if ch0.size else 0.0
                e1 = float(np.mean(np.abs(ch1))) if ch1.size else 0.0
                # if both channels carry significant energy, mix them; otherwise keep ch0
                if ch1.size and e1 > (0.05 * max(e0, 1.0)):
                    audio = ((ch0 + ch1) // 2).astype(np.int16)
                else:
                    # keep left channel
                    audio = ch0.astype(np.int16)

            scores = self._model.predict(audio)
        except Exception as exc:
            logger.debug("openwakeword inference failed: %s", exc)
            return None
        if not isinstance(scores, dict):
            return None
        best_label = None
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
        if best_label and best_score >= self._threshold:
            # optional verifier step
            if self._verifier is not None:
                try:
                    # extract features for verifier using model internals
                    feats = self._model.preprocessor.get_features(self._model.model_inputs.get(best_label))
                    # The verifier expects flattened features per its training pipeline
                    ok = bool(self._verifier.predict([feats.flatten()])[0])
                    if not ok:
                        return None
                except Exception:
                    # on error, fall back to unlverified accept
                    pass
            return best_label
        return None
