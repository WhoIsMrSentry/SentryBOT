from __future__ import annotations

VISION_TOOLS = frozenset({
    "get_vision",
    "get_visual_context",
    "describe_scene",
    "ask_vlm_about_scene",
    "focus_person",
    "remember_person",
})

_FAILURE_MARKERS = (
    "error",
    "unavailable",
    "not available",
    "disconnected",
    "failed",
    "resource busy",
    "vision busy",
    "no matching",
    "no visual",
    "may not be active",
    "endpoint returned error",
    "continue with text-only",
    "vision results unavailable",
    "no known locations",
)

_VISION_SUCCESS_MARKERS = (
    "camera sees:",
    "scene:",
    "people:",
    "hazards:",
    "importance:",
    "visual context refreshed",
    "görüntü işleme gecikti",
    "önümde",
)


def tool_result_succeeded(tool_name: str, result: str) -> bool:
    """Return True only when a tool actually produced a usable outcome."""
    text = str(result or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith("error"):
        return False
    if any(marker in lowered for marker in _FAILURE_MARKERS):
        return False

    name = str(tool_name or "").strip()
    if name in VISION_TOOLS:
        return any(marker in lowered for marker in _VISION_SUCCESS_MARKERS)
    return True


def plan_goal_should_speak(goal: str) -> bool:
    """Skip speculative vision/camera plan lines before any tool runs."""
    text = str(goal or "").strip().lower()
    if not text:
        return False
    blocked = (
        "camera", "vision", "visual", "kamera", "görüntü", "görüntüyü",
        "image", "scene", "sahne", "look", "see", "vlm",
    )
    return not any(word in text for word in blocked)


def subagent_module_should_speak(module: str) -> bool:
    """Do not announce vision-heavy modules before tools prove hardware works."""
    mod = str(module or "").strip().lower()
    return mod not in {"camera", "vlm_bridge", "vlm", "vision_bridge"}
