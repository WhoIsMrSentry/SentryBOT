from modules.autonomy.services.affective_appraisal import AffectiveAppraisal


def test_visual_hazard_maps_to_visual_risk_mood_deltas():
    appraisal = AffectiveAppraisal()

    result = appraisal.process_event("visual_hazard", intensity=0.5)

    assert result["matched"] is True
    assert result["mood_deltas"]["fear"] == 10.0
    assert result["mood_deltas"]["energy"] == 2.5
    assert result["mood_deltas"]["curiosity"] == 1.5
