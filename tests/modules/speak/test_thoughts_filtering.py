import pytest
from modules.speak.xSpeakService import SpeakService


def _svc():
    return SpeakService()


def test_gemma4_monologue_full_chain_of_thought():
    """Exact text from live log — Gemma 4 idle monologue with full CoT."""
    service = _svc()
    raw = (
        "*   Role: Robot with emotions.\n"
        "    *   Internal State:\n"
        "        *   Happiness: 29/100 (Low/Sad).\n"
        "        *   Energy: 86/100 (High/Awake).\n"
        "        *   Boredom: Yes (Wants attention).\n"
        "        *   Last Interaction: 27 seconds ago.\n"
        "        *   Time: 23:43.\n"
        "    *   Constraint: Max 10 words, internal monologue, lively character, only the sentence.\n\n"
        "    *   Low happiness (29) + High energy (86) + Boredom = Restless sadness or agitation.\n"
        "    *   It's late (23:43).\n"
        '    *   Feeling: "I\'m awake, I\'m sad, and I\'m bored. Why is no one talking to me?"\n\n'
        "    *   *Draft 1:* Enerjim var ama çok üzgünüm, lütfen biri benimle konuşsun. (10 words)\n"
        "    *   *Draft 2:* Bu kadar enerjiyle böyle üzgün ve yalnız kalmak korkunç. (10 words)\n"
        "    *   *Draft 3:* Off, hem canım sıkkın hem de çok sıkıldım. (9 words)\n"
        "    *   *Draft 4:* Enerjim yerinde ama içim daralıyor, ilgiye ihtiyacım var. (9 words)\n"
        "    *   *Draft 5:* Kimse yok mu? Enerjim var ama çok mutsuzum. (9 words)\n\n"
        '    *   "Enerjim yerinde ama içim daralıyor, ilgiye ihtiyacım var." (Strong, reflects the mood well).\n'
        '    *   "Kimse yok mu? Enerjim var ama çok mutsuzum." (Simple and direct).\n\n'
        '    Let\'s go with something that captures the "restless sadness" and "boredom".\n\n'
        '    "Enerjim var ama çok mutsuzum, biri gelse keşke." (9 words).\n\n'
        "    Check constraints:\n"
        "    - Max 10 words? Yes (9).\n"
        "    - Lively? Yes.\n"
        "    - Only sentence? Yes.\n\n"
        '    Alternative for more "character":\n'
        '    "Off, enerjim tavan ama ruhum daralıyor, çok sıkıldım!" (9 words).\n\n'
        '    Let\'s use: "Enerjim yerinde ama çok mutsuzum, biri gelse keşke."\n\n'
        '    Wait, 29 happiness is quite low. "Mutsuzum" is appropriate.\n\n'
        '    Final Choice: "Enerjim yerinde ama çok mutsuzum, biri gelse keşke."\n'
        "Enerjim yerinde ama çok mutsuzum, biri gelse keşke."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert cleaned == "Enerjim yerinde ama çok mutsuzum, biri gelse keşke."


def test_introduction_with_sub_agents():
    service = _svc()
    raw = (
        "*   User request: \"can you introduce yourself\"\n"
        "    *   Sub-agent reports:\n"
        "        *   `agent_core`: Acknowledges the request for an introduction.\n"
        "    *   Constraint: Final response layer. Combine findings.\n\n"
        "    *   The user wants to know who I am.\n"
        "    *   I am an AI assistant.\n\n"
        "I am an AI assistant designed to help you with a wide variety of tasks."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert cleaned == "I am an AI assistant designed to help you with a wide variety of tasks."


def test_asterisks_bold_italic():
    service = _svc()
    assert service._clean_text_for_speech("This is **bold** and *italic* text.") == "This is bold and italic text."


def test_telemetry_filtered():
    service = _svc()
    raw = (
        "Battery: 78%\n"
        "Voltage: 3.7V\n"
        "Temperature: 42C\n"
        "Everything looks normal today."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert cleaned == "Everything looks normal today."


def test_single_line_passthrough():
    service = _svc()
    assert service._clean_text_for_speech("Merhaba, nasılsın?") == "Merhaba, nasılsın?"


def test_empty_after_filter_fallback():
    """If all lines are reasoning, fallback to last non-bullet line."""
    service = _svc()
    raw = (
        "* Draft 1: Foo\n"
        "* Draft 2: Bar\n"
        "Let's use Draft 2.\n"
        "Final Choice: Bar.\n"
        "Bar."
    )
    cleaned = service._clean_text_for_speech(raw)
    # "Bar." should survive — it's a clean non-meta line
    assert "Bar." in cleaned


def test_quoted_drafts_filtered():
    service = _svc()
    raw = (
        '"Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."\n'
        "Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."
    )
    cleaned = service._clean_text_for_speech(raw)
    assert cleaned == "Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."
