from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from modules.vision_bridge.services.action_dispatcher import VisionActionDispatcher  # noqa: E402


class DummySemantic:
    def __init__(self, text: str) -> None:
        self.text = text

    def describe(self, results):
        assert results  # ensure we pass detections
        return self.text


def test_emit_scene_dispatches(monkeypatch):
    dispatcher = VisionActionDispatcher("http://localhost:8100/autonomy/apply_actions", timeout=0.1, enabled=True)

    monkeypatch.setattr(
        "modules.vision_bridge.services.action_dispatcher.extract_llm_tags",
        lambda prompt: (prompt.replace("[cmd:head_nod]", ""), {"commands": ["head_nod"]}),
        raising=False,
    )

    captured = {}

    def fake_post(url, json, timeout):  # type: ignore[override]
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout

    monkeypatch.setattr(
        "modules.vision_bridge.services.action_dispatcher.requests.post",
        fake_post,
    )

    dispatcher.emit_scene(DummySemantic("Selam [cmd:head_nod]"), [{"label": "person"}])

    assert captured["url"].endswith("/apply_actions")
    assert captured["json"]["actions"]["commands"] == ["head_nod"]
    assert captured["json"]["text"].strip() == "Selam"
    assert captured["timeout"] == pytest.approx(0.1)


def test_emit_scene_noop_when_disabled(monkeypatch):
    dispatcher = VisionActionDispatcher("http://localhost", timeout=0.1, enabled=False)

    called = False

    def fake_post(*args, **kwargs):  # type: ignore[override]
        nonlocal called
        called = True

    monkeypatch.setattr(
        "modules.vision_bridge.services.action_dispatcher.requests.post",
        fake_post,
    )

    dispatcher.emit_scene(DummySemantic("Hi"), [{"label": "car"}])
    assert called is False
