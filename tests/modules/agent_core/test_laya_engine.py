from unittest.mock import MagicMock
from modules.agent_core.services.laya_engine import LayaEngine, LayaDecision
from modules.agent_core.services.tri_layer import TriLayerRouter, build_subagent_profiles


def _fresh_engine(**kwargs) -> LayaEngine:
    """Creates a fresh LayaEngine instance (bypasses singleton for test isolation)."""
    defaults = {"enabled": True, "confidence_threshold": 0.60}
    defaults.update(kwargs)
    return LayaEngine(**defaults)


def _mock_engine_with_agent(answers: dict, **kwargs) -> LayaEngine:
    """Creates a LayaEngine with a mocked Laya agent returning given answers."""
    engine = _fresh_engine(**kwargs)
    mock_agent = MagicMock()
    mock_agent.system_one.return_value = {"answers": answers}
    engine._agent = mock_agent
    engine._is_available = True
    engine._load_attempted = True
    return engine


# --- LayaDecision dataclass tests ---

def test_laya_decision_properties():
    decision = LayaDecision(
        target_module="emergency_stop",
        module_confidence=0.95,
        is_direct_command=True,
        direct_confidence=0.99,
        affective_event="neutral",
        affect_confidence=0.90,
        urgency_score=2.8,
        urgency_confidence=0.92,
        inference_ms=35.2,
    )
    assert decision.is_emergency is True
    assert decision.is_direct_command is True
    assert decision.target_module == "emergency_stop"


def test_laya_decision_not_emergency():
    decision = LayaDecision(
        target_module="speak",
        module_confidence=0.80,
        is_direct_command=True,
        direct_confidence=0.85,
        affective_event="neutral",
        affect_confidence=0.90,
        urgency_score=0.5,
        urgency_confidence=0.70,
        inference_ms=12.0,
    )
    assert decision.is_emergency is False


def test_laya_decision_uses_configured_emergency_threshold():
    decision = LayaDecision(
        target_module="arduino_serial",
        module_confidence=0.9,
        is_direct_command=True,
        direct_confidence=0.9,
        affective_event="neutral",
        affect_confidence=0.9,
        urgency_score=2.2,
        urgency_confidence=0.9,
        inference_ms=1.0,
        emergency_threshold=2.5,
    )
    assert decision.is_emergency is False


def test_low_confidence_lights_off_false_positive_is_not_emergency():
    decision = LayaDecision(
        target_module="emergency_stop",
        module_confidence=0.8273,
        is_direct_command=True,
        direct_confidence=0.8297,
        affective_event="neutral",
        affect_confidence=0.5,
        urgency_score=2.059,
        urgency_confidence=0.541,
        inference_ms=30.0,
    )

    assert decision.is_emergency is False


def test_confident_direct_emergency_target_works_with_low_score_confidence():
    decision = LayaDecision(
        target_module="emergency_stop",
        module_confidence=0.934,
        is_direct_command=True,
        direct_confidence=0.9818,
        affective_event="neutral",
        affect_confidence=0.5,
        urgency_score=2.2406,
        urgency_confidence=0.1849,
        inference_ms=30.0,
    )

    assert decision.is_emergency is True


# --- Filler and acknowledgment tests ---

def test_laya_engine_instant_fillers_and_acks():
    engine = _fresh_engine()
    # First call should return a non-empty filler
    filler_tr = engine.get_instant_filler("tr")
    assert isinstance(filler_tr, str) and len(filler_tr) > 0

    # Second call within cooldown should return empty (cooldown active)
    filler_again = engine.get_instant_filler("tr")
    assert filler_again == ""

    # Reset cooldown for next test
    engine._last_filler_ts = 0.0
    filler_en = engine.get_instant_filler("en")
    assert isinstance(filler_en, str) and len(filler_en) > 0

    # Acks have no cooldown
    ack_tr = engine.get_fast_ack("tr")
    ack_en = engine.get_fast_ack("en")
    assert isinstance(ack_tr, str) and len(ack_tr) > 0
    assert isinstance(ack_en, str) and len(ack_en) > 0


def test_filler_disabled():
    engine = _fresh_engine(laya_cfg={"filler": {"enabled": False}})
    filler = engine.get_instant_filler("tr")
    assert filler == ""


def test_filler_with_affect_mood_aware():
    engine = _fresh_engine()
    # Joy mood
    filler_joy = engine.get_filler_with_affect("tr", mood="joy")
    assert isinstance(filler_joy, str) and len(filler_joy) > 0

    engine._last_filler_ts = 0.0
    filler_anger = engine.get_filler_with_affect("tr", mood="anger")
    assert isinstance(filler_anger, str) and len(filler_anger) > 0

    engine._last_filler_ts = 0.0
    filler_sad = engine.get_filler_with_affect("en", mood="sadness")
    assert isinstance(filler_sad, str) and len(filler_sad) > 0

    engine._last_filler_ts = 0.0
    filler_fear = engine.get_filler_with_affect("tr", mood="fear")
    assert isinstance(filler_fear, str) and len(filler_fear) > 0


# --- Affective reactions ---

def test_laya_engine_affective_reactions():
    engine = _fresh_engine()
    praise = engine.get_affective_reaction("user_praise")
    assert praise["face"] == "happy"
    assert praise["emotion"] == "joy"
    assert "led_mode" in praise
    assert "body_pose" in praise

    rude = engine.get_affective_reaction("user_rude")
    assert rude["face"] == "sad"
    assert rude["emotion"] == "sorrow"

    neutral = engine.get_affective_reaction("neutral")
    assert neutral["face"] == "neutral"
    assert neutral["led_mode"] == "static"


# --- Mock inference tests ---

NEOPIXEL_ANSWERS = {
    "target_module": {"choice": "neopixel", "confidence": 0.95},
    "is_direct_command": {"choice": "direct_action", "confidence": 0.98},
    "affective_event": {"choice": "neutral", "confidence": 0.90},
    "urgency": {"score": 1.2, "confidence": 0.85},
}


def test_laya_engine_mock_decide_and_fast_path():
    engine = _mock_engine_with_agent(NEOPIXEL_ANSWERS)

    decision = engine.decide("isiklari mavi yap")
    assert decision is not None
    assert decision.target_module == "neopixel"
    assert decision.is_direct_command is True
    assert decision.suggested_tool == "set_lights"

    is_fast, dec = engine.should_fast_path("isiklari mavi yap")
    assert is_fast is True
    assert dec is not None


def test_should_fast_path_uses_world_and_visual_context():
    engine = _mock_engine_with_agent(NEOPIXEL_ANSWERS)
    is_fast, decision = engine.should_fast_path(
        "ışığı değiştir",
        world_state={"battery_percent": 12},
        visual_context="masa üzerinde laptop",
    )

    assert is_fast is True
    assert decision is not None
    sent_text = engine._agent.system_one.call_args[0][0]["text"]
    assert "Sahne: masa üzerinde laptop" in sent_text


def test_emergency_decision_qualifies_for_fast_path():
    answers = {
        "target_module": {"choice": "emergency_stop", "confidence": 0.95},
        "is_direct_command": {"choice": "direct_action", "confidence": 0.96},
        "affective_event": {"choice": "neutral", "confidence": 0.9},
        "urgency": {"score": 2.8, "confidence": 0.95},
    }
    fast, decision = _mock_engine_with_agent(answers).should_fast_path("Dur, tehlike!")
    assert fast is True
    assert decision is not None and decision.is_emergency


def test_confident_direct_hardware_command_qualifies_for_fast_path():
    answers = {
        "target_module": {"choice": "neopixel", "confidence": 0.9},
        "is_direct_command": {"choice": "direct_action", "confidence": 0.92},
        "affective_event": {"choice": "neutral", "confidence": 0.9},
        "urgency": {"score": 0.2, "confidence": 0.8},
    }
    fast, decision = _mock_engine_with_agent(answers).should_fast_path("Işıkları kırmızı yap")
    assert fast is True
    assert decision is not None and decision.is_direct_command


def test_normal_conversation_stays_on_system_two_path():
    answers = {
        "target_module": {"choice": "system2_chat", "confidence": 0.95},
        "is_direct_command": {"choice": "conversation", "confidence": 0.96},
        "affective_event": {"choice": "neutral", "confidence": 0.9},
        "urgency": {"score": 0.1, "confidence": 0.9},
    }
    fast, decision = _mock_engine_with_agent(answers).should_fast_path("Neden gökyüzü mavi?")
    assert fast is False
    assert decision is not None and not decision.is_direct_command


def test_decide_with_context_adjusts_urgency():
    engine = _mock_engine_with_agent({
        "target_module": {"choice": "speak", "confidence": 0.80},
        "is_direct_command": {"choice": "conversation", "confidence": 0.75},
        "affective_event": {"choice": "neutral", "confidence": 0.90},
        "urgency": {"score": 0.5, "confidence": 0.70},
    })

    # Low battery → urgency boosted
    decision = engine.decide_with_context(
        "naber dostum",
        world_state={"battery_percent": 10},
    )
    assert decision is not None
    assert decision.urgency_score >= engine.high_urgency_threshold


def test_decide_with_context_visual_enrichment():
    engine = _mock_engine_with_agent(NEOPIXEL_ANSWERS)

    decision = engine.decide_with_context(
        "isiklari degistir",
        visual_context="2 kişi, masa, laptop",
    )
    assert decision is not None
    # Visual context should be passed to the model
    call_args = engine._agent.system_one.call_args
    assert "Sahne:" in call_args[0][0]["text"]


def test_decide_with_context_follow_active_boosts_camera():
    engine = _mock_engine_with_agent({
        "target_module": {"choice": "camera", "confidence": 0.60},
        "is_direct_command": {"choice": "conversation", "confidence": 0.75},
        "affective_event": {"choice": "neutral", "confidence": 0.90},
        "urgency": {"score": 0.5, "confidence": 0.70},
    })

    decision = engine.decide_with_context(
        "etrafa bak",
        world_state={"follow_active": True},
    )
    assert decision is not None
    assert decision.module_confidence > 0.60  # boosted


# --- Telemetry tests ---

def test_telemetry_tracking():
    engine = _mock_engine_with_agent(NEOPIXEL_ANSWERS)
    engine.decide("isiklari kirmizi yap")
    engine.decide("isiklari mavi yap")

    telemetry = engine.get_telemetry()
    assert telemetry["decision_count"] == 2
    assert telemetry["avg_inference_ms"] >= 0.0
    assert len(telemetry["last_decisions"]) == 2
    assert telemetry["last_target"] == "neopixel"
    assert telemetry["available"] is True
    assert telemetry["enabled"] is True


def test_last_decision_tracked():
    engine = _mock_engine_with_agent(NEOPIXEL_ANSWERS)
    engine.decide("test input")
    assert engine._last_decision is not None
    assert engine._last_decision.target_module == "neopixel"


# --- Urgency gate tests ---

def test_is_urgent_and_emergency():
    engine = _fresh_engine()

    # Not urgent when no decision
    assert engine.is_urgent() is False
    assert engine.is_emergency_decision() is False

    # High urgency decision
    high_urg = LayaDecision(
        target_module="speak", module_confidence=0.80,
        is_direct_command=False, direct_confidence=0.50,
        affective_event="neutral", affect_confidence=0.90,
        urgency_score=1.8, urgency_confidence=0.85, inference_ms=10.0,
    )
    assert engine.is_urgent(high_urg) is True
    assert engine.is_emergency_decision(high_urg) is False

    # Emergency decision
    emergency = LayaDecision(
        target_module="emergency_stop", module_confidence=0.95,
        is_direct_command=True, direct_confidence=0.99,
        affective_event="neutral", affect_confidence=0.90,
        urgency_score=2.5, urgency_confidence=0.92, inference_ms=8.0,
    )
    assert engine.is_urgent(emergency) is True
    assert engine.is_emergency_decision(emergency) is True


def test_low_confidence_high_urgency_chat_is_not_urgent_or_emergency():
    engine = _fresh_engine()
    decision = LayaDecision(
        target_module="speak",
        module_confidence=0.50,
        is_direct_command=False,
        direct_confidence=0.59,
        affective_event="neutral",
        affect_confidence=0.5,
        urgency_score=2.4434,
        urgency_confidence=0.2844,
        inference_ms=30.0,
    )

    assert engine.is_urgent(decision) is False
    assert engine.is_emergency_decision(decision) is False
    assert engine.get_mood_deltas(decision) == {}


# --- Mood deltas tests ---

def test_get_mood_deltas_praise():
    engine = _fresh_engine()
    decision = LayaDecision(
        target_module="system2_chat", module_confidence=0.80,
        is_direct_command=False, direct_confidence=0.40,
        affective_event="user_praise", affect_confidence=0.92,
        urgency_score=0.5, urgency_confidence=0.70, inference_ms=15.0,
    )
    deltas = engine.get_mood_deltas(decision)
    assert deltas["happiness"] > 0
    assert deltas["anger"] < 0
    assert "social_satisfy" in deltas  # system2_chat


def test_get_mood_deltas_emergency():
    engine = _fresh_engine()
    decision = LayaDecision(
        target_module="emergency_stop", module_confidence=0.95,
        is_direct_command=True, direct_confidence=0.99,
        affective_event="neutral", affect_confidence=0.90,
        urgency_score=2.5, urgency_confidence=0.92, inference_ms=8.0,
    )
    deltas = engine.get_mood_deltas(decision)
    assert deltas.get("fear", 0) > 0
    assert deltas.get("energy", 0) < 0
    assert "stimulation_satisfy" in deltas  # direct command


def test_get_mood_deltas_empty_without_decision():
    engine = _fresh_engine()
    deltas = engine.get_mood_deltas()
    assert deltas == {}


# --- Config-driven settings tests ---

def test_config_driven_thresholds():
    cfg = {
        "fast_path": {"enabled": False},
        "urgency": {
            "emergency_threshold": 3.0,
            "high_threshold": 2.0,
            "high_confidence_threshold": 0.7,
            "emergency_target_confidence_threshold": 0.94,
            "emergency_direct_confidence_threshold": 0.85,
            "emergency_urgency_confidence_threshold": 0.92,
        },
        "filler": {"cooldown_s": 5.0, "mood_aware": False},
        "affective": {"mood_impact_scale": 0.5},
    }
    engine = _fresh_engine(laya_cfg=cfg)
    assert engine.fast_path_enabled is False
    assert engine.emergency_threshold == 3.0
    assert engine.high_urgency_threshold == 2.0
    assert engine.high_urgency_confidence_threshold == 0.7
    assert engine.emergency_target_confidence_threshold == 0.94
    assert engine.emergency_direct_confidence_threshold == 0.85
    assert engine.emergency_urgency_confidence_threshold == 0.92
    assert engine.filler_cooldown_s == 5.0
    assert engine.filler_mood_aware is False
    assert engine.mood_impact_scale == 0.5


def test_fast_path_disabled_returns_false():
    cfg = {"fast_path": {"enabled": False}}
    engine = _mock_engine_with_agent(NEOPIXEL_ANSWERS, laya_cfg=cfg)
    engine.fast_path_enabled = False  # ensure it's set
    is_fast, _ = engine.should_fast_path("isiklari mavi yap")
    assert is_fast is False


def test_laya_emergency_threshold_is_configured_on_decision():
    engine = _mock_engine_with_agent({
        "target_module": {"choice": "arduino_serial", "confidence": 0.95},
        "is_direct_command": {"choice": "direct_action", "confidence": 0.95},
        "affective_event": {"choice": "neutral", "confidence": 0.9},
        "urgency": {"score": 2.2, "confidence": 0.9},
    }, laya_cfg={"urgency": {"emergency_threshold": 2.5}})

    decision = engine.decide("dur")
    assert decision is not None
    assert decision.is_emergency is False


# --- TriLayerRouter integration ---

def test_tri_layer_router_with_laya_integration():
    profiles = build_subagent_profiles()
    engine = _mock_engine_with_agent({
        "target_module": {"choice": "arduino_serial", "confidence": 0.92},
        "is_direct_command": {"choice": "direct_action", "confidence": 0.95},
        "affective_event": {"choice": "neutral", "confidence": 0.90},
        "urgency": {"score": 1.5, "confidence": 0.88},
    })

    router = TriLayerRouter(
        profiles=profiles,
        max_subagents=2,
        default_modules=("autonomy", "agent_core"),
        laya_engine=engine,
    )

    routed = router.route("kafanı hafifçe sağa çevir")
    assert "arduino_serial" in routed


def test_laya_engine_extended_affect_palettes():
    engine = _fresh_engine()
    for affect, expected_face in [
        ("anger", "angry"),
        ("disgust", "disgusted"),
        ("joy", "happy"),
        ("fear", "fear"),
        ("curiosity", "curious"),
        ("sadness", "sad"),
    ]:
        reaction = engine.get_affective_reaction(affect)
        assert reaction["face"] == expected_face
        assert reaction["emotion"] in {affect, "joy", "anger", "disgust", "fear", "curiosity", "sorrow"}
        assert reaction["led_color"].startswith("#")
        assert "led_mode" in reaction
        assert "body_pose" in reaction


def test_laya_engine_disgust_urgency_intensity():
    engine = _fresh_engine()
    mild_rx = engine.get_affective_reaction("disgust", urgency=0.5)
    assert mild_rx["emotion"] == "disgust"
    assert mild_rx["led_color"] in engine.palettes["disgust"]["mild"]

    intense_rx = engine.get_affective_reaction("disgust", urgency=2.0)
    assert intense_rx["emotion"] == "disgust"
    assert intense_rx["led_color"] in engine.palettes["disgust"]["intense"]


def test_laya_engine_extended_mood_deltas():
    engine = _fresh_engine()
    from types import SimpleNamespace

    dec_disgust = SimpleNamespace(affective_event="disgust", is_emergency=False, urgency_score=1.0, urgency_confidence=0.9, is_direct_command=False, target_module="other")
    deltas = engine.get_mood_deltas(dec_disgust)
    assert deltas.get("anger", 0) > 0
    assert deltas.get("happiness", 0) < 0

    dec_fear = SimpleNamespace(affective_event="fear", is_emergency=False, urgency_score=1.0, urgency_confidence=0.9, is_direct_command=False, target_module="other")
    deltas_fear = engine.get_mood_deltas(dec_fear)
    assert deltas_fear.get("fear", 0) > 0

    dec_curiosity = SimpleNamespace(affective_event="curiosity", is_emergency=False, urgency_score=1.0, urgency_confidence=0.9, is_direct_command=False, target_module="other")
    deltas_curious = engine.get_mood_deltas(dec_curiosity)
    assert deltas_curious.get("curiosity", 0) > 0


def test_hardware_tools_turkish_colors():
    from modules.agent_core.services.tools.hardware_tools import _normalize_rgb

    assert _normalize_rgb("kırmızı") == [255, 0, 0]
    assert _normalize_rgb("kirmizi") == [255, 0, 0]
    assert _normalize_rgb("yeşil") == [0, 255, 0]
    assert _normalize_rgb("yesil") == [0, 255, 0]
    assert _normalize_rgb("mavi") == [0, 0, 255]
    assert _normalize_rgb("sarı") == [255, 255, 0]
    assert _normalize_rgb("kapalı") == [0, 0, 0]

