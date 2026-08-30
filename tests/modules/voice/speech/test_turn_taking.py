import pytest
from modules.voice.speech.services.turn_taking import DynamicTurnTakingEngine, TurnState

def test_turn_taking_speech_and_completion():
    engine = DynamicTurnTakingEngine(min_speech_duration_s=0.5, end_of_turn_silence_s=0.8)
    engine.start_listening(current_time_s=0.0)
    
    # User speaks at t=0.1
    res1 = engine.process_vad_frame(is_speech=True, current_time_s=0.1)
    assert res1["state"] == TurnState.USER_SPEAKING
    assert not res1["turn_completed"]

    # User still speaking at t=0.8
    res2 = engine.process_vad_frame(is_speech=True, current_time_s=0.8)
    assert res2["state"] == TurnState.USER_SPEAKING

    # Silence at t=1.0 (0.2s silence - not done yet)
    res3 = engine.process_vad_frame(is_speech=False, current_time_s=1.0)
    assert res3["state"] == TurnState.USER_PAUSED
    assert not res3["turn_completed"]

    # Silence at t=1.7 (0.9s silence > 0.8s threshold -> turn done!)
    res4 = engine.process_vad_frame(is_speech=False, current_time_s=1.7)
    assert res4["state"] == TurnState.USER_DONE
    assert res4["turn_completed"]

def test_turn_taking_hesitation_prompt_cue():
    engine = DynamicTurnTakingEngine(min_speech_duration_s=0.2, end_of_turn_silence_s=3.0, hesitation_pause_s=1.5)
    engine.start_listening(current_time_s=0.0)
    
    engine.process_vad_frame(is_speech=True, current_time_s=0.1)
    
    # Pause for 1.6s
    res = engine.process_vad_frame(is_speech=False, current_time_s=1.7)
    assert res["state"] == TurnState.PROMPT_CUE
    assert res["suggested_cue"] == "head_tilt_listening"
