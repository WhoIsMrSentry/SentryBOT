from __future__ import annotations

# sentrybot_batch06e_no_hardware_wakeword_asset_guard
def _sentrybot_batch06e_skip_wakeword_assets():
    import os as _os
    return (
        str(_os.getenv("SENTRYBOT_NO_HARDWARE", "")).lower() in {"1", "true", "yes", "on"}
        or str(_os.getenv("SENTRYBOT_SKIP_WAKEWORD_AUTOSTART", "")).lower() in {"1", "true", "yes", "on"}
    )


import importlib
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("wakeword.openwakeword_assets")

_OWW_RELEASE = "v0.5.1"
_OWW_BASE = f"https://github.com/dscripka/openWakeWord/releases/download/{_OWW_RELEASE}"

BUILTIN_FEATURE_MODELS_ONNX: Dict[str, dict] = {
    "melspectrogram": {
        "download_url": f"{_OWW_BASE}/melspectrogram.onnx",
        "filename": "melspectrogram.onnx",
    },
    "embedding": {
        "download_url": f"{_OWW_BASE}/embedding_model.onnx",
        "filename": "embedding_model.onnx",
    },
}
BUILTIN_FEATURE_MODELS_TFLITE: Dict[str, dict] = {
    "melspectrogram": {
        "download_url": f"{_OWW_BASE}/melspectrogram.tflite",
        "filename": "melspectrogram.tflite",
    },
    "embedding": {
        "download_url": f"{_OWW_BASE}/embedding_model.tflite",
        "filename": "embedding_model.tflite",
    },
}
BUILTIN_VAD_MODELS: Dict[str, dict] = {
    "silero_vad": {
        "download_url": f"{_OWW_BASE}/silero_vad.onnx",
        "filename": "silero_vad.onnx",
    },
}
BUILTIN_WAKE_MODELS_ONNX: Dict[str, dict] = {
    "hey_mycroft": {
        "download_url": f"{_OWW_BASE}/hey_mycroft_v0.1.onnx",
        "filename": "hey_mycroft_v0.1.onnx",
    },
}
BUILTIN_WAKE_MODELS_TFLITE: Dict[str, dict] = {
    "hey_mycroft": {
        "download_url": f"{_OWW_BASE}/hey_mycroft_v0.1.tflite",
        "filename": "hey_mycroft_v0.1.tflite",
    },
}
BUILTIN_WAKE_MODELS = BUILTIN_WAKE_MODELS_ONNX


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


def _module_models_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "models"


def _builtin_wake_models(use_onnx: bool) -> Dict[str, dict]:
    return BUILTIN_WAKE_MODELS_ONNX if use_onnx else BUILTIN_WAKE_MODELS_TFLITE


def _openwakeword_catalog(use_onnx: bool = True) -> dict:
    try:
        import openwakeword  # type: ignore

        catalog = getattr(openwakeword, "MODELS", {}) or {}
        if catalog:
            return dict(catalog)
    except Exception:
        pass
    module_dir = _module_models_dir()
    return {
        key: {
            "model_path": str(module_dir / str(meta["filename"])),
            "download_url": str(meta["download_url"]),
        }
        for key, meta in _builtin_wake_models(use_onnx).items()
    }


def _feature_model_groups(use_onnx: bool = True) -> list[dict]:
    try:
        import openwakeword  # type: ignore
    except Exception:
        openwakeword = None  # type: ignore
    groups: list[dict] = []
    if openwakeword is not None:
        feat = getattr(openwakeword, "FEATURE_MODELS", {}) or {}
        vad = getattr(openwakeword, "VAD_MODELS", {}) or {}
        if feat:
            groups.append(dict(feat))
        if vad:
            groups.append(dict(vad))
    if not groups:
        feat_builtin = BUILTIN_FEATURE_MODELS_ONNX if use_onnx else BUILTIN_FEATURE_MODELS_TFLITE
        groups = [feat_builtin, BUILTIN_VAD_MODELS]
    return groups


def _openwakeword_pkg_dir() -> Path:
    ow_pkg = importlib.import_module("openwakeword")
    return Path(getattr(ow_pkg, "__file__", "")).resolve().parent


def _openwakeword_models_dir() -> Path:
    return _openwakeword_pkg_dir() / "resources" / "models"


def _download_url(url: str, dest: Path, min_bytes: int = 1024) -> None:
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return
    if dest.exists():
        try:
            dest.unlink()
        except Exception:
            pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request

    logger.info("downloading openwakeword asset: %s", dest.name)
    urllib.request.urlretrieve(url, dest)
    if not dest.exists() or dest.stat().st_size < min_bytes:
        raise RuntimeError(f"openwakeword download incomplete: {dest.name}")


def _framework_asset_url(url: str, use_onnx: bool) -> tuple[str, str]:
    fname = url.rsplit("/", 1)[-1]
    if use_onnx:
        if fname.endswith(".tflite"):
            fname = fname[:-7] + ".onnx"
            url = url.replace(".tflite", ".onnx")
    elif fname.endswith(".onnx"):
        fname = fname[:-5] + ".tflite"
        url = url.replace(".onnx", ".tflite")
    return url, fname


def _download_framework_asset(url: str, target_dir: Path, use_onnx: bool) -> None:
    asset_url, fname = _framework_asset_url(url, use_onnx)
    _download_url(asset_url, target_dir / fname)


def _try_utils_download_models(model_names: list[str]) -> bool:
    try:
        import openwakeword  # type: ignore
    except Exception:
        return False

    utils_mod = getattr(openwakeword, "utils", None)
    download_fn = getattr(utils_mod, "download_models", None) if utils_mod is not None else None
    if download_fn is None:
        try:
            from openwakeword.utils import download_models as download_fn  # type: ignore
        except Exception:
            download_fn = None
    if download_fn is None:
        return False

    for args, kwargs in (
        ((), {"model_names": model_names}),
        ((model_names,), {}),
        ((), {}),
    ):
        try:
            download_fn(*args, **kwargs)
            return True
        except TypeError:
            continue
        except Exception as exc:
            logger.debug("openwakeword.utils.download_models failed: %s", exc)
            return False
    return False


def _ensure_openwakeword_assets(model_names: list[str], use_onnx: bool) -> None:
    # sentrybot_batch06e_return_before_download
    if _sentrybot_batch06e_skip_wakeword_assets():
        return {
            "ok": True,
            "skipped": True,
            "reason": "hardware_disabled",
        }

    if _try_utils_download_models(model_names):
        return

    targets = [_openwakeword_models_dir(), _module_models_dir()]
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)

    for group in _feature_model_groups(use_onnx):
        for entry in group.values():
            if isinstance(entry, dict) and entry.get("download_url"):
                for target in targets:
                    _download_framework_asset(str(entry["download_url"]), target, use_onnx)

    catalog = _openwakeword_catalog(use_onnx)
    for name in model_names:
        entry = catalog.get(name)
        if isinstance(entry, dict) and entry.get("download_url"):
            for target in targets:
                _download_framework_asset(str(entry["download_url"]), target, use_onnx)


def _normalize_pretrained_names(model_names: list, catalog: dict) -> list[str]:
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
    return normalized


def _resolve_pretrained_models(
    model_names: list,
    inference_framework: str = "onnx",
) -> tuple[Dict[str, str], list[str]]:
    try:
        import openwakeword  # type: ignore  # noqa: F401
    except Exception as exc:
        raise RuntimeError(f"openwakeword is required for pretrained models: {exc}") from exc

    use_onnx = str(inference_framework or "onnx").strip().lower() == "onnx"
    catalog = _openwakeword_catalog(use_onnx)
    if not catalog:
        raise RuntimeError("openwakeword model catalog is empty")

    normalized = _normalize_pretrained_names(model_names, catalog)
    _ensure_openwakeword_assets(normalized, use_onnx)

    resolved: Dict[str, str] = {}
    ext = ".onnx" if use_onnx else ".tflite"
    for key in normalized:
        entry = catalog[key]
        candidates: list[Path] = []
        builtin_fname = _builtin_wake_models(use_onnx).get(key, {}).get("filename")
        if builtin_fname:
            stem = Path(str(builtin_fname)).stem
            for root in (_openwakeword_models_dir(), _module_models_dir()):
                candidates.append(root / f"{stem}{ext}")
        base_path = Path(str(entry.get("model_path", "")))
        if base_path.name:
            candidates.append(base_path.with_suffix(ext))
            if base_path.suffix != ext:
                candidates.append(base_path)
        chosen = next((p for p in candidates if p.exists() and p.stat().st_size >= 1024), None)
        if chosen is None:
            raise FileNotFoundError(f"openwakeword model missing after download: {key}")
        if use_onnx and chosen.suffix.lower() != ".onnx":
            raise FileNotFoundError(f"openwakeword onnx model missing (found {chosen.name}): {key}")
        resolved[key] = str(chosen.resolve())
    return resolved, normalized


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
