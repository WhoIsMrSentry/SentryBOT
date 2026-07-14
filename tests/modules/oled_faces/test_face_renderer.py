"""FaceRenderer unit tests — display init and brightness wiring."""

from unittest.mock import MagicMock, patch


def test_face_renderer_begin_uses_config_brightness():
    from modules.oled_faces.services.face_renderer import FaceRenderer

    with patch("modules.oled_faces.services.face_renderer.PiSsd1306Driver") as driver_cls, patch(
        "modules.oled_faces.services.face_renderer.EyeEngine"
    ) as engine_cls:
        driver = MagicMock()
        driver.begin.return_value = True
        driver.width = 128
        driver.height = 64
        driver_cls.return_value = driver

        renderer = FaceRenderer({"brightness": 120, "fps": 30})
        assert renderer.begin() is True
        engine_cls.assert_called_once()
        assert engine_cls.call_args.kwargs["bright"] == 120
        assert engine_cls.call_args.kwargs["fps"] == 30
