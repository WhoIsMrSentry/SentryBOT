"""Visual context importance is derived from scene content, not hardcoded."""

from __future__ import annotations

from modules.vlm_bridge.services.processor import VisionProcessor
from modules.vlm_bridge.services.visual_context import VisualContextCache


def _proc_with_cache():
    proc = VisionProcessor.__new__(VisionProcessor)
    proc.visual_context_cache = VisualContextCache(max_history=3)
    proc._follow_active = False
    return proc


def test_hazard_scene_scores_higher_than_empty_scene():
    proc = _proc_with_cache()

    proc.update_visual_context({"summary": "empty room", "people": [], "objects": [], "hazards": []})
    empty = proc.visual_context_cache.get_latest().importance_score

    proc.update_visual_context(
        {"summary": "knife nearby", "people": [], "objects": [],
         "hazards": [{"label": "knife", "distance_m": 0.4}]}
    )
    hazard = proc.visual_context_cache.get_latest().importance_score

    assert hazard > empty
    assert hazard >= 0.7  # hazard weight dominates


def test_owner_present_raises_importance():
    proc = _proc_with_cache()
    proc.update_visual_context(
        {"summary": "owner here", "objects": [], "hazards": [],
         "people": [{"name": "Emir", "recognition_level": 6, "confidence": 0.9}]}
    )
    score = proc.visual_context_cache.get_latest().importance_score
    assert score >= 0.4


def test_caller_high_importance_is_not_downgraded():
    proc = _proc_with_cache()
    # An empty scene would derive low importance, but an explicit user question
    # must keep a high floor.
    proc.update_visual_context(
        {"summary": "nothing", "people": [], "objects": [], "hazards": [], "importance_score": 0.9},
        is_user_question=True,
    )
    assert proc.visual_context_cache.get_latest().importance_score >= 0.9
