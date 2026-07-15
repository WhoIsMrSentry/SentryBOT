from __future__ import annotations

from modules.agent_core.services.progress import ProgressManager
from modules.agent_core.services.tool_progress import tool_result_succeeded


def test_tool_result_succeeded_rejects_unavailable_vision() -> None:
    assert not tool_result_succeeded(
        "get_vision",
        "Vision results unavailable. Continue with text-only reasoning if needed.",
    )
    assert not tool_result_succeeded(
        "get_visual_context",
        "No visual context available yet. Camera may not be active.",
    )


def test_tool_result_succeeded_accepts_real_vision_payload() -> None:
    assert tool_result_succeeded("get_vision", "Vision: person, chair")
    assert tool_result_succeeded("get_visual_context", "Scene: kitchen | People: Ali")


def test_progress_skips_tool_done_without_success() -> None:
    spoken = []

    class _SpeechStub:
        def enqueue_progress(self, text, cancel_token="", language=""):
            spoken.append(text)

        def cancel_by_token(self, _token):
            return 0

    pm = ProgressManager(speech_arbiter=_SpeechStub())
    token = pm.new_request()
    pm.emit_tool_done(token, "get_vision", "Vision results unavailable.")
    assert spoken == []


def test_progress_speaks_tool_done_after_success() -> None:
    spoken = []

    class _SpeechStub:
        def enqueue_progress(self, text, cancel_token="", language=""):
            spoken.append(text)

        def cancel_by_token(self, _token):
            return 0

    pm = ProgressManager(speech_arbiter=_SpeechStub())
    token = pm.new_request(language="tr")
    pm.emit_tool_done(token, "get_vision", "Vision: table")
    assert spoken == ["Görüntüyü aldım."]
