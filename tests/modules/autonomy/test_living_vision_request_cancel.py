from modules.autonomy.services.brain import AutonomyBrain


def test_request_id_switch_marks_old_inactive():
    brain = AutonomyBrain({"llm": {"enabled": False}, "vision_hooks": {"enabled": False}})
    brain._active_speech_req_id = "old_req"
    assert brain._is_active_request("old_req") is True
    brain._active_speech_req_id = "new_req"
    assert brain._is_active_request("old_req") is False
    assert brain._is_active_request("new_req") is True
