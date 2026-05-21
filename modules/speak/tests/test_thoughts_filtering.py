import pytest
from modules.speak.xSpeakService import SpeakService

def test_thoughts_filtering():
    service = SpeakService()

    # Introduction case
    intro_text = (
        "*   User request: \"can you introduce yourself\"\n"
        "    *   Sub-agent reports:\n"
        "        *   `agent_core`: Acknowledges the request for an introduction.\n"
        "    *   Constraint: Final response layer. Combine findings.\n\n"
        "    *   The user wants to know who I am.\n"
        "    *   I am an AI assistant.\n\n"
        "I am an AI assistant designed to help you with a wide variety of tasks."
    )
    cleaned = service._clean_text_for_speech(intro_text)
    assert cleaned == "I am an AI assistant designed to help you with a wide variety of tasks."

    # Monologue case
    monologue_text = (
        "*   Role: A robot with emotions.\n"
        "    *   Happiness: 32/100\n\n"
        "    *   Happiness is low.\n\n"
        '    *Selection:* "Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."\n\n'
        '    "Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."\n\n'
        "Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."
    )
    cleaned = service._clean_text_for_speech(monologue_text)
    assert cleaned == "Enerjim tavan ama canım çok sıkkın, ilgi istiyorum."

    # Asterisks removal case
    bold_text = "This is **bold** and *italic* text."
    cleaned = service._clean_text_for_speech(bold_text)
    assert cleaned == "This is bold and italic text."
