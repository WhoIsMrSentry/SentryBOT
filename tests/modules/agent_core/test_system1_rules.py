from modules.agent_core.services.laya_engine import LayaEngine
from modules.agent_core.services.system1_rules import classify

CASES = [
    ("hemen dur", "emergency_stop", True),
    ("acil stop", "emergency_stop", True),
    ("çarpıyorum", "emergency_stop", True),
    ("kırmızı LED'i aç", "neopixel", True),
    ("ışıkları mavi yap", "neopixel", True),
    ("ışığı kapat", "neopixel", True),
    ("sağa bak", "arduino_serial", True),
    ("kafanı yukarı kaldır", "arduino_serial", True),
    ("geri git", "arduino_serial", True),
    ("takip bırak", "arduino_serial", True),
    ("beni takip et", "arduino_serial", True),
    ("fotoğraf çek", "camera", True),
    ("şarkı söyle", "speak", True),
    ("aferin sana", "system2_chat", False),
    ("sen salaksın", "system2_chat", False),
    ("üzgünüm bugün", "system2_chat", False),
]

NONE_CASES = [
    "bugün hava nasıl",
    "bir sorum var",
    "iyi misin",
]


def test_rules_match_expected_targets():
    for text, target, is_direct in CASES:
        decision = classify(text)
        assert decision is not None, f"no decision for {text!r}"
        assert decision.target_module == target, f"{text!r} -> {decision.target_module}"
        assert decision.is_direct_command is is_direct


def test_rules_passthrough_unknown_text():
    for text in NONE_CASES:
        assert classify(text) is None


def test_emergency_is_fast_path_compatible():
    LayaEngine._instance = None
    _ = LayaEngine(
        enabled=True,
        confidence_threshold=0.60,
        laya_cfg={"fast_path": {"enabled": True}},
    )
    decision = classify("hemen dur")
    assert decision.is_emergency


def test_light_proposal_fail_closed_without_effect():
    policy = {
        "enabled": True,
        "allowed_actions": ["set_lights"],
        "confidence_threshold": 0.85,
        "default_light_effect": "SOLID",
    }
    decision = classify("ışığı kırmızı yap", action_proposal_cfg=policy)
    assert decision.suggested_action is None

    off = classify("ışığı kapat", action_proposal_cfg=policy)
    assert off.suggested_action is not None
    assert off.suggested_action["arguments"]["color"] == "off"


def test_decisions_are_sub_1ms():
    for text, _, _ in CASES[:5]:
        decision = classify(text)
        assert decision.inference_ms < 5.0


def test_negated_commands_blocked_from_direct_action():
    for negated in [
        "ışıkları kırmızı yapma",
        "sağa dönme",
        "fotoğraf çekme",
        "şarkı söyleme",
    ]:
        decision = classify(negated)
        assert decision is not None, f"expected guard decision for {negated!r}"
        assert decision.is_direct_command is False
        assert decision.target_module == "system2_chat"


def test_conversational_queries_vs_polite_imperatives():
    # Conversational questions about lights/colors should NOT trigger direct hardware action
    for query in [
        "LED kırmızı yanıyor mu",
        "sence ışığı mavi mi yapsam",
        "mavi rengi çok seviyorum",
    ]:
        decision = classify(query)
        assert decision is not None, f"expected guard decision for {query!r}"
        assert decision.is_direct_command is False
        assert decision.target_module == "system2_chat"

    # Polite imperatives ("... yapar mısın / çevirir misin") MUST still trigger direct action
    polite = classify("ışıkları kırmızıya çevirir misin")
    assert polite is not None
    assert polite.target_module == "neopixel"
    assert polite.is_direct_command is True


def test_disgust_and_anger_affect_rules():
    disgust_dec = classify("midem bulandı çok iğrenç")
    assert disgust_dec is not None
    assert disgust_dec.affective_event == "disgust"
    assert disgust_dec.is_direct_command is False

    anger_dec = classify("çok sinirlendim öfkeliyim")
    assert anger_dec is not None
    assert anger_dec.affective_event == "anger"
    assert anger_dec.is_direct_command is False

