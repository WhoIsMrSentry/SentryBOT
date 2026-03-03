from modules.oled_faces.services.mapper import FaceMapper


def test_mapper_has_full_catalog():
    mapper = FaceMapper({})
    assert len(mapper.catalog_bitmaps) >= 32
    assert "normal" in mapper.catalog_bitmaps
    assert "all" in mapper.catalog_animations
