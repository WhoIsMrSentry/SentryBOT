import tempfile
import numpy as np

from modules.vlm_bridge.services.yunet_detector import (
    get_yunet_detector,
    get_sface_recognizer,
)
from modules.vlm_bridge.services.face_manager import FaceManager


def test_yunet_detector_initialization():
    detector = get_yunet_detector()
    assert detector is not None
    # If the model is downloaded, is_available should be True
    if detector.is_available:
        assert detector._detector is not None


def test_yunet_detector_blank_frame():
    detector = get_yunet_detector()
    blank = np.zeros((320, 320, 3), dtype=np.uint8)
    boxes = detector.detect(blank)
    assert isinstance(boxes, list)
    # A black blank image should have 0 detected faces
    assert len(boxes) == 0


def test_yunet_detector_invalid_input():
    detector = get_yunet_detector()
    assert detector.detect(None) == []
    assert detector.detect(np.zeros((0, 0, 3), dtype=np.uint8)) == []


def test_sface_recognizer_synthetic_matching():
    sface = get_sface_recognizer()
    assert sface is not None

    # Test dummy 128D embeddings matching (uses numpy fallback if model weights missing)
    vec1 = np.ones((1, 128), dtype=np.float32)
    vec2 = np.ones((1, 128), dtype=np.float32)
    score = sface.match(vec1, vec2)
    assert score > 0.99  # Identical vectors should have cosine score near 1.0

    # Orthogonal vectors
    vec_diff = np.zeros((1, 128), dtype=np.float32)
    vec_diff[0, 0] = 1.0
    vec_diff2 = np.zeros((1, 128), dtype=np.float32)
    vec_diff2[0, 1] = 1.0
    score_diff = sface.match(vec_diff, vec_diff2)
    assert score_diff < 0.1


def test_face_manager_with_yunet_and_sface():
    with tempfile.TemporaryDirectory() as td:
        fm = FaceManager(data_dir=td, filename="faces.json")
        assert hasattr(fm, "_yunet")
        assert hasattr(fm, "_sface")
        assert hasattr(fm, "_known_embeddings")

        # Manually register an embedding for a person
        dummy_vec = np.ones((1, 128), dtype=np.float32)
        dummy_vec = dummy_vec / np.linalg.norm(dummy_vec)
        fm._known_embeddings["Tester"] = dummy_vec
        fm.known_face_names.append("Tester")

        # Test identifying when embedding is stored
        # If no face is in the test image, it should return Unknown gracefully
        test_face = np.full((120, 120, 3), 180, dtype=np.uint8)
        name, score = fm.identify_face_with_score(test_face)
        assert isinstance(name, str)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

        # Test saving and loading back
        fm.save_faces()
        fm2 = FaceManager(data_dir=td, filename="faces.json")
        try:
            assert "Tester" in fm2.known_face_names or "Tester" in fm2._known_embeddings
        finally:
            fm.close()
            fm2.close()


def test_processor_detect_face_boxes_fallback():
    from modules.vlm_bridge.services.processor_identity import ProcessorIdentityMixin

    class DummyProcessor(ProcessorIdentityMixin):
        def __init__(self):
            self._face_cascade = None

    proc = DummyProcessor()
    # Blank frame with no cascade or faces detected should return empty list without crashing
    dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    boxes = proc._detect_face_boxes(dummy_frame)
    assert isinstance(boxes, list)
