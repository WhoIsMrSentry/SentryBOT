from __future__ import annotations

from pathlib import Path

from modules.speak.config_loader import _resolve_piper_paths
from modules.speak.services.tts import PiperBackend


def test_resolve_piper_voice_entry() -> None:
    cfg = {
        "voice": "glados",
        "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
        "voices": {
            "glados": {
                "model_path": "data/piper_models/en-glados-medium/glados_piper_medium.onnx",
                "config_path": "data/piper_models/en-glados-medium/glados_piper_medium.onnx.json",
            },
        },
    }
    resolved = PiperBackend._resolve_voice_cfg(cfg)
    assert resolved["model_path"].endswith("glados_piper_medium.onnx")


def test_resolve_piper_paths_expands_repo_relative() -> None:
    piper = _resolve_piper_paths(
        {
            "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
            "voices": {
                "tr": {
                    "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
                },
            },
        }
    )
    assert Path(piper["model_path"]).is_absolute()
    assert Path(piper["voices"]["tr"]["model_path"]).is_absolute()
