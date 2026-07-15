from modules.agent_core.services.tri_layer import TriLayerRouter, build_subagent_profiles


def test_tri_layer_profiles_cover_core_modules():
    profiles = build_subagent_profiles()
    expected = {
        "agent_core",
        "autonomy",
        "hardware",
        "neopixel",
        "speech",
        "speak",
        "camera",
        "vlm_bridge",
        "wakeword",
        "gateway",
    }
    assert expected.issubset(set(profiles.keys()))


def test_tri_layer_router_keyword_selection():
    profiles = build_subagent_profiles()
    router = TriLayerRouter(profiles=profiles, max_subagents=2, default_modules=("autonomy", "agent_core"))

    routed = router.route("turn head and set neopixel light wave")

    assert len(routed) == 2
    assert "hardware" in routed or "piservo" in routed or "arduino_serial" in routed
    assert "neopixel" in routed or "animate" in routed or "interactions" in routed


def test_tri_layer_router_fallback_selection():
    profiles = build_subagent_profiles()
    router = TriLayerRouter(profiles=profiles, max_subagents=2, default_modules=("autonomy", "agent_core"))

    routed = router.route("hello there")

    assert routed == ["autonomy", "agent_core"]


def test_tri_layer_router_respects_max_subagents():
    profiles = build_subagent_profiles()
    router = TriLayerRouter(profiles=profiles, max_subagents=1, default_modules=("autonomy", "agent_core"))

    routed = router.route("vision and wakeword and light and hardware")

    assert len(routed) == 1
