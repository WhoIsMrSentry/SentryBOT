from __future__ import annotations

from modules.vlm_bridge.services.processor import VisionProcessor


def test_remote_tasks_strip_semantic_scene_when_budget_not_allowed():
    p = VisionProcessor({
        "vision": {
            "processing_mode": "remote",
            "mode_categories": {
                "remote": {
                    "objects": True,
                    "people": True,
                    "faces": True,
                    "hazards": True,
                    "semantic_scene": True,
                }
            },
        },
        "vision_llm": {"enabled": False},
        "vision_semantic_budget": {"enabled": True},
    })
    cheap = p._remote_requested_tasks(run_semantic_vlm=False)
    semantic = p._remote_requested_tasks(run_semantic_vlm=True)
    assert "semantic_scene" not in cheap
    assert "semantic_scene" in semantic
    assert "hazards" in cheap


def test_semantic_budget_reasons_default_to_user_hazard_not_scene_change():
    p = VisionProcessor({"vision_llm": {"enabled": False}})
    assert p._semantic_budget_allows(question="what is here", reason="scene_change") is True
    assert p._semantic_budget_allows(question="", reason="hazard") is True
    assert p._semantic_budget_allows(question="", reason="new_person") is True
    assert p._semantic_budget_allows(question="", reason="scene_change") is False
    assert p._semantic_budget_allows(question="", reason="idle_refresh") is False
