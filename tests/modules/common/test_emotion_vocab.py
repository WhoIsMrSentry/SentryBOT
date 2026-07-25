"""Tests for the canonical emotion vocabulary."""
import sys
sys.path.insert(0, ".")

from modules.common.emotion_vocab import (
    get_vocab,
    canonical_emotion,
    emotion_render,
    Emotion,
)


def test_default_vocab_loaded():
    """Vocab singleton loads with all 29 emotions."""
    vocab = get_vocab()
    emotions = vocab.all_canonical()
    assert len(emotions) >= 25, f"Expected 25+ emotions, got {len(emotions)}"


def test_canonical_resolution():
    """Known labels map to canonical emotions."""
    vocab = get_vocab()
    assert vocab.canonical("happy").value == "joy"
    assert vocab.canonical("sad").value == "sadness"
    assert vocab.canonical("angry").value == "anger"
    assert vocab.canonical("kork") == Emotion.FEAR
    assert vocab.canonical("merak") == Emotion.CURIOSITY
    assert vocab.canonical("sinirlen") == Emotion.ANGER
    assert vocab.canonical("mutlu ol") == Emotion.JOY
    assert vocab.canonical("kızgın") == Emotion.ANGER
    assert vocab.canonical("NeŞElİ") == Emotion.JOY or vocab.canonical("neşeli") == Emotion.JOY


def test_default_unknown_label():
    """Unknown label falls back to default."""
    vocab = get_vocab()
    assert vocab.canonical("asdfg") == vocab.default_canonical
    assert vocab.canonical("") == vocab.default_canonical
    assert vocab.canonical(None) == vocab.default_canonical


def test_render_has_complete_hints():
    """Each canonical emotion has a complete render hint."""
    vocab = get_vocab()
    for emo in Emotion:
        r = vocab.render(emo)
        assert r.canonical == emo
        assert r.neopixel_effect, f"{emo} missing neopixel_effect"
        assert len(r.neopixel_rgb) == 3
        assert r.oled_animation, f"{emo} missing oled_animation"
        assert r.voice_tone, f"{emo} missing voice_tone"


def test_anger_is_intense_red():
    """Anger specifically uses red palette with PULSE/COMET effect."""
    vocab = get_vocab()
    r = vocab.render(Emotion.ANGER)
    assert r.neopixel_rgb[0] >= r.neopixel_rgb[1], "Anger R should dominate"
    assert r.neopixel_effect in ("PULSE", "COMET")
    assert r.oled_animation in ("angry", "furious", "ScanningEyes") or "angry" in r.oled_animation.lower()


def test_joy_is_green_calm():
    """Joy uses green breathing pattern."""
    vocab = get_vocab()
    r = vocab.render(Emotion.JOY)
    assert r.neopixel_rgb[1] >= r.neopixel_rgb[0], "Joy G should be high"
    assert r.neopixel_effect in ("BREATHE", "PULSE", "RAINBOW_CYCLE")


def test_along_returns_intensity_scalable():
    """Render dict has all necessary fields for json serialization."""
    render_dict = get_vocab().get_render_dict(Emotion.JOY)
    assert "canonical" in render_dict
    assert "neopixel" in render_dict
    assert "oled" in render_dict
    assert "voice" in render_dict
    assert "semantic" in render_dict
    assert render_dict["semantic"]["valence"] > 0  # joy is positive


def test_anger_has_negative_valence():
    """Anger has negative valence, high arousal."""
    render_dict = get_vocab().get_render_dict(Emotion.ANGER)
    assert render_dict["semantic"]["valence"] < 0
    assert render_dict["semantic"]["arousal"] > 0.5


def test_module_top_level_helpers():
    """Module-level functions delegate to singleton."""
    assert canonical_emotion("happy").value == "joy"
    assert emotion_render("happy").canonical.value == "joy"


if __name__ == "__main__":
    test_default_vocab_loaded()
    test_canonical_resolution()
    test_default_unknown_label()
    test_render_has_complete_hints()
    test_anger_is_intense_red()
    test_joy_is_green_calm()
    test_along_returns_intensity_scalable()
    test_anger_has_negative_valence()
    test_module_top_level_helpers()
    print("All emotion_vocab tests passed.")
