"""Tests for runtime mutation of :class:`TriLayerRouter.max_subagents`."""

from __future__ import annotations

from modules.agent_core.services.tri_layer import (
    SubAgentProfile,
    TriLayerRouter,
    build_subagent_profiles,
)


def test_set_max_clamps_to_bounds():
    router = TriLayerRouter(profiles=build_subagent_profiles(), max_subagents=1)
    assert router.set_max(3) == 3
    assert router.set_max(0) == 1
    assert router.set_max(99) <= 8


def test_route_respects_max_subagents():
    profiles = build_subagent_profiles()
    router = TriLayerRouter(profiles=profiles, max_subagents=1)
    chosen = router.route("kamera ile bak ve etrafi tani")
    assert len(chosen) == 1
    router.set_max(3)
    chosen = router.route("kamera ile bak ve etrafi tani")
    assert len(chosen) <= 3
    assert len(chosen) >= 1
