import sys
from unittest.mock import MagicMock, patch

from modules.wakeword.services.openwakeword_runner import _resolve_pretrained_models


def test_resolve_pretrained_models_hey_mycroft(tmp_path) -> None:
    onnx_path = tmp_path / "hey_mycroft_v0.1.onnx"
    onnx_path.write_bytes(b"model")

    fake_models = {
        "hey_mycroft": {
            "model_path": str(tmp_path / "hey_mycroft_v0.1.tflite"),
            "download_url": "https://example/hey_mycroft_v0.1.tflite",
        }
    }
    mock_utils = MagicMock()
    mock_ow = MagicMock()
    mock_ow.MODELS = fake_models

    with patch.dict(
        sys.modules,
        {"openwakeword": mock_ow, "openwakeword.utils": mock_utils},
    ):
        resolved = _resolve_pretrained_models(["hey_mycroft"], "onnx")

    mock_utils.download_models.assert_called_once_with(model_names=["hey_mycroft"])
    assert resolved["hey_mycroft"] == str(onnx_path.resolve())
