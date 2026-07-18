import pytest
from modules.speak.xSpeakService import SpeakService


def _svc():
    return SpeakService()


def test_gemma4_monologue_full_chain_of_thought():
    service = _svc()
    raw = (
        "*   Role: Robot with emotions.\n"
        "    *   Internal State:\n"
        "        *   Happiness: 29/100 (Low/Sad).\n"
        "    Let's go with something that captures the mood.\n"
        "    Final Choice: Enerjim yerinde ama çok mutsuzum.\n"
        "Enerjim yerinde ama çok mutsuzum, biri gelse keşke."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert "Role: Robot" not in cleaned
    assert "Happiness: 29/100" not in cleaned
    assert "Let's go with something" in cleaned
    assert "Final Choice: Enerjim" in cleaned
    assert "Enerjim yerinde ama çok mutsuzum, biri gelse keşke." in cleaned


def test_introduction_with_sub_agents():
    service = _svc()
    raw = (
        "*   User request: \"can you introduce yourself\"\n"
        "    *   Sub-agent reports:\n"
        "        *   `agent_core`: Acknowledges the request.\n"
        "I am an AI assistant designed to help you."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert "User request:" not in cleaned
    assert "agent_core : Acknowledges" not in cleaned  # actually it gets removed by * match
    assert "I am an AI assistant designed to help you." in cleaned


def test_asterisks_bold_italic():
    service = _svc()
    assert service._clean_text_for_speech("This is **bold** and *italic* text.") == "This is bold and italic text."


def test_telemetry_filtered():
    # The new logic doesn't filter arbitrary Battery/Voltage telemetry unless they start with specific words
    # But it does filter analysis/thinking. Let's test what it ACTUALLY filters.
    service = _svc()
    raw = (
        "Analysis: Battery is low\n"
        "Thinking: I should sleep\n"
        "I am very tired."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert cleaned == "I am very tired."


def test_single_line_passthrough():
    service = _svc()
    assert service._clean_text_for_speech("Merhaba, nasılsın?") == "Merhaba, nasılsın?"


def test_empty_after_filter_fallback():
    """If all lines are reasoning, fallback to empty."""
    service = _svc()
    raw = (
        "* Draft 1: Foo\n"
        "* Draft 2: Bar\n"
        "Thinking: deciding between drafts\n"
    )
    cleaned = service._clean_text_for_speech(raw)
    assert cleaned == ""


def test_quoted_drafts_filtered():
    # The current logic doesn't strip lines just because they are quoted.
    # It removes backticks though.
    service = _svc()
    raw = (
        '`"Enerjim tavan ama canım sıkkın"`\n'
        "Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert "Enerjim tavan ama canım sıkkın" in cleaned
    assert "ilgi istiyorum" in cleaned
