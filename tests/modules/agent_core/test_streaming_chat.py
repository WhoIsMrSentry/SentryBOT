"""Tests for token-stream chat and companion line generation."""
from __future__ import annotations

from unittest.mock import MagicMock

from modules.agent_core.services.agent import AgentOrchestrator
from modules.autonomy.services.companion_lines import CompanionLineGenerator


def test_chat_maybe_stream_emits_sentences():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.persona_stream_enabled = True
    agent.llm_provider = "ollama"
    agent._pick_runtime_model = lambda m: m  # type: ignore

    chunks = [
        {"message": {"content": "Merhaba. "}},
        {"message": {"content": "Nasılsın?"}},
    ]
    agent.ollama_client = MagicMock()
    agent.ollama_client.chat.return_value = iter(chunks)

    spoken = []

    def _on_sentence(text: str, idx: int) -> None:
        spoken.append((idx, text))

    out = agent._chat_maybe_stream(
        "test-model",
        [{"role": "user", "content": "selam"}],
        None,
        {"num_predict": 32},
        on_sentence=_on_sentence,
    )
    assert out["message"]["content"] == "Merhaba. Nasılsın?"
    assert len(spoken) >= 1


def test_companion_needs_line_high_social():
    gen = CompanionLineGenerator(None, {"use_llm": False})
    line = gen._needs_line(
        "proactive",
        {"needs": {"social": 80}, "speaker": "Ali", "dominant_emotion": "neutral"},
    )
    assert line and "sohbet" in line.lower()
