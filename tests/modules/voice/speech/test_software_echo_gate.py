import time
import numpy as np
import pytest

from modules.voice.speech.services.audio_filters import SoftwareEchoGate, SpeechAudioFilterMixin


def test_software_echo_gate_inactive():
    gate = SoftwareEchoGate(suppression_gain=0.1, barge_in_ratio=2.0)
    # When TTS is not playing, audio should pass through unchanged
    pcm = np.full(160, 500, dtype=np.int16).tobytes()
    out, barge = gate.process_chunk(pcm, input_rms=500.0)
    assert out == pcm
    assert barge is False


def test_software_echo_gate_attenuation():
    gate = SoftwareEchoGate(suppression_gain=0.1, barge_in_ratio=2.0)
    gate.set_tts_playback(active=True, estimated_rms=1000.0)

    # Low amplitude speech / speaker echo (rms 800 < 1000 * 2.0)
    pcm = np.full(160, 800, dtype=np.int16).tobytes()
    out, barge = gate.process_chunk(pcm, input_rms=800.0)
    assert barge is False
    # The output chunk should be attenuated (smaller amplitude)
    out_arr = np.frombuffer(out, dtype=np.int16)
    assert np.all(np.abs(out_arr) <= 100)


def test_software_echo_gate_barge_in_breakthrough():
    gate = SoftwareEchoGate(suppression_gain=0.1, barge_in_ratio=2.0)
    gate.set_tts_playback(active=True, estimated_rms=1000.0)

    # Human shouting/speaking loudly over robot (rms 2500 >= 1000 * 2.0)
    pcm = np.full(160, 2500, dtype=np.int16).tobytes()
    out, barge = gate.process_chunk(pcm, input_rms=2500.0)
    assert barge is True
    # The output chunk should NOT be attenuated because user broke through
    assert out == pcm


def test_speech_audio_filter_mixin_echo_gate_wiring():
    class DummySpeechService(SpeechAudioFilterMixin):
        def __init__(self):
            self.cfg = {}
            self._direction = None
            self._auto_language = False
            self._utterance_pcm = bytearray()
            self._max_utterance_bytes = 16000
            self._stt_input_gain = 1.0
            self._echo_gate = SoftwareEchoGate(suppression_gain=0.1, barge_in_ratio=2.0)

    svc = DummySpeechService()
    svc.set_tts_playback_state(True, estimated_rms=1000.0)
    assert svc._echo_gate._tts_playing is True

