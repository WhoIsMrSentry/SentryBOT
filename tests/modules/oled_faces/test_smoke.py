from modules.oled_faces.services.mapper import FaceMapper


def test_mapper_has_full_catalog():
    from modules.oled_faces.config_loader import load_config

    mapper = FaceMapper(load_config())
    assert len(mapper.catalog_bitmaps) >= 31
    assert "normal" in mapper.catalog_bitmaps
    assert "cool" in mapper.catalog_bitmaps
    assert "scan" in mapper.catalog_animations
    assert "editing" in mapper.catalog_animations
    assert "smoke" in mapper.catalog_animations


def test_canonical_emotion_resolves_to_face():
    mapper = FaceMapper({})
    assert mapper.from_emotions(["joy"]).name == "happy"
    assert mapper.from_emotions(["tired"]).name == "tired"
    assert mapper.from_emotions(["anger"]).name == "angry"


def test_explicit_event_map_override_wins():
    mapper = FaceMapper({"event_map": {"emotion:happy": {"mode": "bitmap", "name": "kawaii"}}})
    assert mapper.from_emotions(["happy"]).name == "kawaii"
