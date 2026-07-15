from fastapi.testclient import TestClient

from modules.piservo.xPiServoService import create_app


def test_healthz():
    app = create_app()
    client = TestClient(app)
    r = client.get("/piservo/healthz")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_set_angles():
    app = create_app()
    client = TestClient(app)
    r = client.post("/piservo/set", params={"left": 90, "right": 90})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_ear_pose_resolves_emotion_aliases():
    from modules.piservo.services.ears import EMOTION_POSES, pose_for_emotion

    # canonical labels map straight through
    assert pose_for_emotion("joy") == EMOTION_POSES["joy"]
    # aliases resolve via the shared vocabulary
    assert pose_for_emotion("happy") == EMOTION_POSES["joy"]
    assert pose_for_emotion("scared") == EMOTION_POSES["fear"]
    assert pose_for_emotion("angry") == EMOTION_POSES["anger"]
    # tired has no dedicated pose -> mapped onto sadness ears
    assert pose_for_emotion("tired") == EMOTION_POSES["sadness"]
    # unknown -> neutral
    assert pose_for_emotion("???") == EMOTION_POSES["neutral"]
