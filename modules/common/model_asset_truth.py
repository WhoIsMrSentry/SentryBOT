
from __future__ import annotations
import importlib.util
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MANIFEST: Dict[str, Any] = {
    "assets": {
        "piper_tr": {"kind": "file_pair", "required": True, "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx", "config_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx.json", "purpose": "Turkish Piper TTS voice"},
        "vosk_tr": {"kind": "directory", "required": True, "path": "modules/speech/models/vosk-tr", "purpose": "Primary Turkish STT model"},
        "vosk_en": {"kind": "directory", "required": False, "path": "modules/speech/models/vosk-en", "purpose": "Optional English STT model"},
        "imx500_object_model": {"kind": "file", "required": True, "path": "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk", "purpose": "Raspberry Pi AI Camera IMX500 object model"},
    },
    "python_modules": {
        "picamera2": {"required": True, "purpose": "Raspberry Pi camera pipeline"},
        "piper": {"required": True, "purpose": "Persistent Piper Python runtime"},
        "vosk": {"required": True, "purpose": "Speech recognition"},
        "openwakeword": {"required": False, "purpose": "Wakeword engine"},
        "numpy": {"required": True, "purpose": "Audio and vision processing"},
    },
    "commands": {
        "aplay": {"required": True, "purpose": "Audio playback"},
        "arecord": {"required": True, "purpose": "Audio capture"},
        "ollama": {"required": False, "purpose": "Local/remote LLM client"},
    },
}

def _root() -> Path:
    return Path(__file__).resolve().parents[2]

def _load_manifest(root: Path) -> Dict[str, Any]:
    path = root / "config" / "model_assets.json"
    merged = json.loads(json.dumps(DEFAULT_MANIFEST))
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("assets", "python_modules", "commands"):
                    if isinstance(data.get(key), dict):
                        merged[key].update(data[key])
        except Exception:
            pass
    return merged

def _resolve(root: Path, raw: Any) -> Path:
    p = Path(str(raw or ""))
    return p if p.is_absolute() else root / p

def _check_asset(root: Path, name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(spec.get("kind") or "file")
    out = {"name": name, "kind": kind, "required": bool(spec.get("required", False)), "purpose": spec.get("purpose", ""), "ok": False}
    if kind == "file_pair":
        model = _resolve(root, spec.get("model_path"))
        cfg = _resolve(root, spec.get("config_path"))
        out.update({"model_path": str(model), "config_path": str(cfg), "model_exists": model.is_file(), "config_exists": cfg.is_file()})
        out["ok"] = bool(model.is_file() and cfg.is_file())
        return out
    path = _resolve(root, spec.get("path"))
    out["path"] = str(path)
    out["ok"] = bool(path.is_dir() and any(path.iterdir())) if kind == "directory" and path.exists() else bool(path.is_file())
    return out

def _check_module(name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": name, "ok": importlib.util.find_spec(name) is not None, "required": bool(spec.get("required", False)), "purpose": spec.get("purpose", "")}

def _check_command(name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    found = shutil.which(name)
    return {"name": name, "ok": bool(found), "path": found or "", "required": bool(spec.get("required", False)), "purpose": spec.get("purpose", "")}

def collect_asset_truth(project_root: Optional[str | Path] = None) -> Dict[str, Any]:
    root = Path(project_root).resolve() if project_root else _root()
    manifest = _load_manifest(root)
    assets = [_check_asset(root, n, s) for n, s in manifest.get("assets", {}).items() if isinstance(s, dict)]
    modules = [_check_module(n, s) for n, s in manifest.get("python_modules", {}).items() if isinstance(s, dict)]
    commands = [_check_command(n, s) for n, s in manifest.get("commands", {}).items() if isinstance(s, dict)]
    items: List[Dict[str, Any]] = assets + modules + commands
    required_missing = [x for x in items if x.get("required") and not x.get("ok")]
    optional_missing = [x for x in items if not x.get("required") and not x.get("ok")]
    return {"ok": not required_missing, "available": True, "project_root": str(root), "python": sys.version.split()[0], "platform": platform.platform(), "assets": assets, "python_modules": modules, "commands": commands, "required_missing": required_missing, "optional_missing": optional_missing, "summary": {"required_missing_count": len(required_missing), "optional_missing_count": len(optional_missing), "total_checked": len(items)}}

if __name__ == "__main__":
    print(json.dumps(collect_asset_truth(Path.cwd()), ensure_ascii=False, indent=2))
