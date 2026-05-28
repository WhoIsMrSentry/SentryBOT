"""Tests for the procedural face fallback rasteriser."""

from __future__ import annotations

from modules.oled_faces.services.procedural_face import draw_face


def _render(name: str, w: int = 128, h: int = 64):
    pixels = set()

    def plot(x: int, y: int) -> None:
        if 0 <= x < w and 0 <= y < h:
            pixels.add((x, y))

    style = draw_face(name, w, h, plot)
    return pixels, style


def test_draws_within_bounds_and_non_empty():
    pixels, _ = _render("normal")
    assert pixels, "expected the face to draw at least some pixels"
    for x, y in pixels:
        assert 0 <= x < 128 and 0 <= y < 64


def test_emotions_produce_distinct_faces():
    happy, _ = _render("happy")
    sad, _ = _render("sad")
    angry, _ = _render("angry")
    surprised, _ = _render("surprised")
    # different expressions must not be pixel-identical
    assert happy != sad
    assert happy != angry
    assert sad != surprised


def test_aliases_match_canonical_via_vocab():
    # 'happy' is a direct pose; 'joy' resolves through the vocab to the same look
    happy, _ = _render("happy")
    joy, _ = _render("joy")
    assert happy == joy


def test_blink_is_minimal():
    blink, style = _render("blink")
    normal, _ = _render("normal")
    # closed eyes should draw fewer pixels than open eyes
    assert len(blink) < len(normal)
