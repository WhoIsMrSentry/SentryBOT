import pytest
from unittest.mock import MagicMock

from modules.gateway.services.bootstrap_ai import _wire_multimodal_identity
from modules.voice.speaker_id.services.identity_fusion import ActiveSpeakerResolver


def test_multimodal_identity_wiring_and_fusion():
    resolver = ActiveSpeakerResolver()
    speaker_id_mock = MagicMock()
    speaker_id_mock.identity_resolver = resolver

    brain_mock = MagicMock()
    autonomy_mock = MagicMock()
    autonomy_mock.brain = brain_mock

    vlm_bridge_mock = MagicMock()
    event_bus_mock = MagicMock()
    vlm_bridge_mock.event_bus = event_bus_mock

    arduino_mock = MagicMock()
    arduino_mock._event_handlers = []

    started = {
        "speaker_id": speaker_id_mock,
        "autonomy": autonomy_mock,
        "vlm_bridge": vlm_bridge_mock,
        "arduino": arduino_mock,
    }

    _wire_multimodal_identity(started)

    # 1. AutonomyBrain receives identity_resolver
    assert brain_mock.identity_resolver is resolver

    # 2. VLM event bus subscription was established
    event_bus_mock.subscribe_all.assert_called_once()
    vlm_callback = event_bus_mock.subscribe_all.call_args[0][0]

    # 3. Arduino RFID handler was attached
    assert len(arduino_mock._event_handlers) == 1
    rfid_callback = arduino_mock._event_handlers[0]

    # Test multi-modal consensus
    # Trigger face detection of "Emir"
    vlm_callback("person_seen", {"name": "Emir", "confidence": 0.85})
    res_face = resolver.resolve()
    assert res_face["person_id"] == "Emir"
    assert res_face["modalities"] == ["face"]

    # Trigger voice match of "Emir"
    resolver.observe_voice("Emir", confidence=0.80)
    res_multi = resolver.resolve()
    assert res_multi["person_id"] == "Emir"
    # Modality consensus bonus (+0.15) should raise confidence
    assert res_multi["confidence"] > 0.85
    assert set(res_multi["modalities"]) == {"face", "voice"}

    # Trigger RFID match
    rfid_callback({"event": "rfid", "uid": "EMIR_CARD_123"})
    res_rfid = resolver.resolve()
    assert res_rfid["active"] is True

