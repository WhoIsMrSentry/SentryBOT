from modules.oled_faces.services.mapper import FaceMapper


def test_mapper_has_full_catalog():
    mapper = FaceMapper({})
    assert len(mapper.catalog_bitmaps) >= 32
    assert "normal" in mapper.catalog_bitmaps
    assert "all" in mapper.catalog_animations


def test_canonical_emotion_resolves_to_face():
    # autonomy emits canonical labels (joy/tired/anger) that have no direct
    # `emotion:<label>` entry; they must still land on a real bitmap.
    mapper = FaceMapper({})
    assert mapper.from_emotions(["joy"]).name == "happy"
    assert mapper.from_emotions(["tired"]).name == "sleepy"
    assert mapper.from_emotions(["anger"]).name == "angry"


def test_explicit_event_map_override_wins():
    mapper = FaceMapper({"event_map": {"emotion:happy": {"mode": "bitmap", "name": "excited"}}})
    assert mapper.from_emotions(["happy"]).name == "excited"
