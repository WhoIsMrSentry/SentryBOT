from __future__ import annotations

from pathlib import Path
import sys
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from modules.autonomy.services import palette_store  # noqa: E402


def test_set_palette_creates_missing_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text("{}", encoding="utf-8")

    palettes = palette_store.set_palette("sunrise", [16, 32, 64], config_path)

    assert palettes["sunrise"] == [16, 32, 64]
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["defaults"]["lights"]["palettes"]["sunrise"] == [16, 32, 64]


def test_remove_palette_and_validation(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
        defaults:
          lights:
            palettes:
              arctic: [255, 255, 255]
        """.strip(),
        encoding="utf-8",
    )

    palettes = palette_store.remove_palette("arctic", config_path)
    assert "arctic" not in palettes

    with pytest.raises(KeyError):
        palette_store.remove_palette("arctic", config_path)

    with pytest.raises(ValueError):
        palette_store.set_palette("bad", [10, 20], config_path)
