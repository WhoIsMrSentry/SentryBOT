from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from modules.agent_core.services.laya_engine import LayaDecision
from modules.agent_core.services.laya_action_contract import (
    build_laya_action_proposal,
)

logger = logging.getLogger("agent.system1_rules")

_UNSPECIFIED = "unspecified"

_COLOR_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "red": ("kırmızı", "kestane", "red"),
    "green": ("yeşil", "green"),
    "blue": ("mavi", "blue"),
    "yellow": ("sarı", "yellow"),
    "orange": ("turuncu", "orange"),
    "purple": ("mor", "purple"),
    "pink": ("pembe", "pink"),
    "cyan": ("camgöbeği", "cyan"),
    "teal": ("turkuaz", "teal"),
    "magenta": ("fuşya", "magenta", "macenta"),
    "white": ("beyaz", "white"),
}

_LIGHT_TOKEN = re.compile(
    r"\b(ışık\w*|ışığ\w*|lamba\w*|neon\w*|şerit\w*|rgb|led\w*|neopixel\w*)\b"
)

_LIGHT_TOGGLE_OFF = re.compile(
    r"\b(ışık\w*|ışığ\w*|lamba\w*|led\w*|neopixel\w*)\b.*\b(kapat\w*|söndür\w*|kapalı\s+(?:yap\w*|duruma\s+getir\w*|kalsın|olsun))\b"
)

_LIGHT_ACTION_VERB = re.compile(
    r"\b(yap\w*|yak\w*|aç\w*|kapat\w*|söndür\w*|çevir\w*|ayarla\w*|al|boya\w*|getir\w*|olsun|yansın|parlasın|kıs\w*|artır\w*|değiştir\w*|geç\w*)\b"
)

_NEGATED_COMMAND_RE = re.compile(
    r"\b(yapma\w*|açma\w*|kapatma\w*|söndürme\w*|yakma\w*|çevirme\w*|dönme\w*|bakma\w*|gitme\w*|gelme\w*|yürüme\w*|çekme\w*|çalma\w*|söyleme\w*|olmasın|sakın\s+(?:yap|aç|kapat|yak|çevir|git|söyle))\b"
)

_POLITE_IMPERATIVE_RE = re.compile(
    r"\b\w+(?:abilir|ebilir|ar|er|ır|ir|ur|ür|r)\s+m[ıi]s[ıi]n(?:ız|iz)?\b"
)

_CONVERSATIONAL_QUERY_RE = re.compile(
    r"(?:\b(?:sence|acaba|nasıl|neden|niçin|niye|nedir|ne\s+renk|anlamı\s+ne|güvenli\s+mi|zarar\w*\s+m[ıi]|var\s+m[ıi]|yanıyor\s+mu|seviyorum|en\s+sevdiğim|hakkında\s+konuş\w*|tarif\s+et\w*|bana\s+.*anlat\w*)\b|\bm[ıi]\s+yap(?:sam|sak|alım)\b|\byap(?:sam|sak)\s+m[ıi]\b)"
)

_EFFECT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "COMET": ("kuyruk", "comet"),
    "PULSE": ("darbe", "atış", "pulse", "yılan"),
    "WAVE": ("dalga", "wave"),
    "SOLID": ("sabit", "düz", "solid"),
    "OFF": ("kapat", "söndür", "off"),
    "BREATHE": ("nefes", "soluk", "breathe"),
    "RANDOM_BLINK": ("rastgele", "yanıp", "blink"),
    "TWINKLE": ("parıltı", "parlaklık", "twinkle", "kıpır"),
}

_EMERGENCY_ANCHORED = re.compile(
    r"^(?:(?:hemen|acil(?:en)?|derhal|lütfen)\s+)?(?:robot\s+)?(?:dur|stop|estop|halt|acil\s+stop|emergency\s+stop)\b[\s!.,:;]*"
)
_EMERGENCY_PANIC = re.compile(
    r"\b(düşüyorum|düşeceksin|çarp(?:ıyorum|ıyoruz|acaksın|acak)|tehlike(?:nin)?\s+var|motor(?:ları|u)?\s+acil\s+durdur|acil\s+durdur)\b"
)
_EMERGENCY_WORD_LIMIT = 6

_HEAD_PATTERNS: Tuple[str, ...] = (
    r"\bkafa(?:nı|ını)?\s+(?:sağa|sola|yukarı|aşağı)\s+(?:çevir|dön|kaldır|indir)\b",
    r"\bbaşını\s+(?:sağa|sola|yukarı|aşağı)\s+çevir\b",
    r"\b(?:sağa|sola|yukarı|aşağı)\s+(?:bak|bakış|çevir|dön)\b",
    r"\b(?:look|turn)\s+(?:left|right|up|down)\b",
    r"\bhead\s+(?:left|right|up|down)\b",
)

_MOTION_PATTERNS: Tuple[str, ...] = (
    r"\b(?:ileri|geri)\s+(?:git|gel|yürü)\b",
    r"\b(?:sağa|sola)\s+dön\b",
    r"\b(?:yürü|koş|dolaş|gezin)\b",
    r"\btakip\s+(?:et|başla)\b",
    r"\bbeni\s+(?:takip|izle)me?\b",
    r"\bfollow\s+me\b",
    r"\b(?:sağa|sola|ileri|geri)\s+(?:hareket|manevra)\b",
)

_FOLLOW_STOP_PATTERNS: Tuple[str, ...] = (
    r"\btakip(?:çi(?:si)?)?\s+(?:bırak|etme)\w*\b",
    r"\bfollow(?:ing)?\s+stop\b",
    r"\bstop\s+(?:following|tracking)\b",
)

_CAMERA_DIRECT_PATTERNS: Tuple[str, ...] = (
    r"\b(?:fotoğraf(?:ını)?|resim(?:ini)?|kamera(?:yı)?)\s+(?:çek|başla|aç)\b",
    r"\b(?:başla|kaydet)\s+(?:kamera|görüntü|kayıt)\b",
    r"\btake\s+(?:a\s+)?(?:photo|picture|photo)\b",
)

_CAMERA_SOFT_PATTERNS: Tuple[str, ...] = (
    r"\bne\s+(?:görüyorsun|görüyor|bakıyorsun)\b",
    r"\betafa\s+bak\b",
    r"\b(?:yüz(?:ler)?|faces?|nesneler?)\s+(?:var\s+|gör|ara|tanı)\b",
    r"\bwhat\s+do\s+you\s+see\b",
    r"\bkamera\s+(?:görüntüsü|bakış)\b",
)

_SPEAK_DIRECT_PATTERNS: Tuple[str, ...] = (
    r"\b(?:şarkı|müzik|melodi)\s+(?:söyle|çal|başla|koy)\b",
    r"\bsing\s+(?:a\s+)?(?:song|music)\b",
    r"\b(?:sus|sesi\s+kapat|sessize\s+geç|konuşmayı\s+durdur)\b",
    r"\b(?:be\s+)?quiet\b",
)

_SPEAK_SOFT_PATTERNS: Tuple[str, ...] = (
    r"\b(?:bir\s+şey|biri|şey)\s+söyle\b",
    r"\b(?:bana\s+)?(?:konuş|anlat)\s+(?:bana|bak)\b",
)

_AFFECT_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "user_praise": (
        r"\b(?:aferin\w*|bravo\w*|harika\w*|süper\w*|muhteşem\w*|tebrik(?:ler)?\w*|teşekkür\w*|sağol\w*|seni\s+seviyorum|love\s+you|good\s+job|great|awesome|perfect)\b",
    ),
    "user_rude": (
        r"\b(?:aptal\w*|salak\w*|ahmak\w*|eşek\w*|gerizekalı\w*|kullanışsız\w*|lanet\w*|stupid|shut\s+up|useless|idiot|dumb)\b",
    ),
    "anger": (
        r"\b(?:sinir\w*|öfke\w*|kızgın\w*|delir\w*|çıldır\w*|nefret\w*|kahretsin|angry|furious|mad)\b",
    ),
    "disgust": (
        r"\b(?:iğrenç\w*|tiksin\w*|mide(?:m|mi)\s+bulan\w*|leş\s+gibi|berbat\w*|kusmuk\w*|pis\s+kok\w*|çürük\w*|disgust\w*|gross|yuck)\b",
    ),
    "sadness": (
        r"\b(?:üzgün\w*|mutsuz\w*|yalnız\w*|keder\w*|kaygılı\w*|depressed|lonely|sad)\b",
    ),
    "fear": (
        r"\b(?:kork\w*|panik\w*|ürk\w*|ödüm\s+koptu|scared|afraid|panic)\b",
    ),
    "curiosity": (
        r"\b(?:merak\w*|anlat\w*|curious|ne\s+b(?:u|iliyor)\w*)\b",
    ),
    "joy": (
        r"\b(?:mutlu\w*|neşeli\w*|sevinç\w*|gülümse\w*|kıpır\s+kıpır|happy|joyful)\b",
    ),
}

_URGENT_KEYWORDS = re.compile(r"\b(?:hemen|derhal|acil(?:en)?|acele|hızlı|quick|now|fast)\b")

_HEAD_RE = tuple(re.compile(p, re.IGNORECASE) for p in _HEAD_PATTERNS)
_MOTION_RE = tuple(re.compile(p, re.IGNORECASE) for p in _MOTION_PATTERNS)
_FOLLOW_STOP_RE = tuple(re.compile(p, re.IGNORECASE) for p in _FOLLOW_STOP_PATTERNS)
_CAMERA_DIRECT_RE = tuple(re.compile(p, re.IGNORECASE) for p in _CAMERA_DIRECT_PATTERNS)
_CAMERA_SOFT_RE = tuple(re.compile(p, re.IGNORECASE) for p in _CAMERA_SOFT_PATTERNS)
_SPEAK_DIRECT_RE = tuple(re.compile(p, re.IGNORECASE) for p in _SPEAK_DIRECT_PATTERNS)
_SPEAK_SOFT_RE = tuple(re.compile(p, re.IGNORECASE) for p in _SPEAK_SOFT_PATTERNS)
_AFFECT_RE = {k: tuple(re.compile(p, re.IGNORECASE) for p in v) for k, v in _AFFECT_PATTERNS.items()}


def _norm_text(text: str) -> str:
    return str(text or "").strip().casefold().replace("\u0307", "")


def _search(text: str, patterns: Tuple[re.Pattern[str], ...]) -> Optional[re.Pattern[str]]:
    for pattern in patterns:
        if pattern.search(text):
            return pattern
    return None


def _first_color(text: str) -> Optional[str]:
    for color, keywords in _COLOR_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword), text):
                return color
    return None


def _first_effect(text: str) -> Optional[str]:
    for effect, keywords in _EFFECT_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword), text):
                return effect
    return None


def _urgency_bonus(text: str) -> float:
    return 1.5 if _URGENT_KEYWORDS.search(text) else 0.0


def is_negated_command(text: str) -> bool:
    """Return True when the utterance is a negated Turkish imperative (e.g. 'yapma', 'açma')."""
    cleaned = _norm_text(text)
    if not cleaned or _search(cleaned, _FOLLOW_STOP_RE):
        return False
    return bool(_NEGATED_COMMAND_RE.search(cleaned))


def is_conversational_query(text: str) -> bool:
    """Return True when the utterance is a conversational question/opinion rather than a polite command."""
    cleaned = _norm_text(text)
    if not cleaned:
        return False
    if _POLITE_IMPERATIVE_RE.search(cleaned):
        return False
    return bool(_CONVERSATIONAL_QUERY_RE.search(cleaned))


def classify(
    text: str,
    *,
    action_proposal_cfg: Optional[Dict[str, Any]] = None,
) -> Optional[LayaDecision]:
    """Instant (<1ms) rule-based System 1 classifier.

    Mirrors the LayaDecision contract exactly. Returns None when no rule
    applies, letting upstream cascade fall to the embedding or neural layer.
    """
    cleaned = _norm_text(text)
    if not cleaned:
        return None

    t0 = time.perf_counter()
    urgency = _urgency_bonus(cleaned)

    if _EMERGENCY_ANCHORED.match(cleaned) and len(cleaned.split()) <= _EMERGENCY_WORD_LIMIT:
        return _build_decision(
            rule="emergency_command",
            text=text,
            target_module="emergency_stop",
            target_confidence=0.95,
            direct=True,
            direct_confidence=0.95,
            urgency=max(3.0, urgency),
            urgency_confidence=0.90,
            t0=t0,
        )

    if _EMERGENCY_PANIC.search(cleaned):
        return _build_decision(
            rule="emergency_panic",
            text=text,
            target_module="emergency_stop",
            target_confidence=0.92,
            direct=True,
            direct_confidence=0.90,
            urgency=3.0,
            urgency_confidence=0.88,
            t0=t0,
        )

    if _search(cleaned, _FOLLOW_STOP_RE):
        return _build_decision(
            rule="follow_stop",
            text=text,
            target_module="arduino_serial",
            target_confidence=0.90,
            direct=True,
            direct_confidence=0.88,
            urgency=_urgency_bonus(cleaned),
            urgency_confidence=0.85,
            t0=t0,
            suggested_tool="stop_follow",
        )

    if is_negated_command(cleaned):
        return _build_decision(
            rule="negated_command_guard",
            text=text,
            target_module="system2_chat",
            target_confidence=0.88,
            direct=False,
            direct_confidence=0.90,
            urgency=urgency,
            urgency_confidence=0.70,
            t0=t0,
        )

    color = _first_color(cleaned)
    effect = _first_effect(cleaned)
    has_light_token = bool(_LIGHT_TOKEN.search(cleaned))
    has_light_verb = bool(_LIGHT_ACTION_VERB.search(cleaned))

    if is_conversational_query(cleaned) and (
        has_light_token
        or color is not None
        or _search(cleaned, _HEAD_RE) is not None
        or _search(cleaned, _MOTION_RE) is not None
        or _search(cleaned, _CAMERA_DIRECT_RE) is not None
        or _search(cleaned, _SPEAK_DIRECT_RE) is not None
    ):
        return _build_decision(
            rule="conversational_query_guard",
            text=text,
            target_module="system2_chat",
            target_confidence=0.85,
            direct=False,
            direct_confidence=0.88,
            urgency=urgency,
            urgency_confidence=0.65,
            t0=t0,
        )

    if _search(cleaned, _HEAD_RE):
        return _build_decision(
            rule="head_motion",
            text=text,
            target_module="arduino_serial",
            target_confidence=0.90,
            direct=True,
            direct_confidence=0.90,
            urgency=_urgency_bonus(cleaned),
            urgency_confidence=0.85,
            t0=t0,
        )

    if _search(cleaned, _MOTION_RE):
        return _build_decision(
            rule="motor_motion",
            text=text,
            target_module="arduino_serial",
            target_confidence=0.90,
            direct=True,
            direct_confidence=0.90,
            urgency=_urgency_bonus(cleaned),
            urgency_confidence=0.85,
            t0=t0,
        )

    if _light_toggle_off(cleaned):
        return _build_light_decision(
            text=text,
            t0=t0,
            urgency=urgency,
            color="off",
            effect="OFF",
            rule="light_toggle_off",
            action_proposal_cfg=action_proposal_cfg,
        )

    if color is not None and (has_light_token or has_light_verb):
        if has_light_verb or len(cleaned.split()) <= 4:
            return _build_light_decision(
                text=text,
                t0=t0,
                urgency=urgency,
                color=color,
                effect=effect,
                rule="light_color_direct",
                action_proposal_cfg=action_proposal_cfg,
            )

    if has_light_token and (has_light_verb or effect is not None):
        return _build_decision(
            rule="light_generic",
            text=text,
            target_module="neopixel",
            target_confidence=0.75,
            direct=True,
            direct_confidence=0.70,
            urgency=urgency,
            urgency_confidence=0.65,
            t0=t0,
        )

    if _search(cleaned, _CAMERA_DIRECT_RE):
        return _build_decision(
            rule="camera_direct",
            text=text,
            target_module="camera",
            target_confidence=0.92,
            direct=True,
            direct_confidence=0.90,
            urgency=urgency,
            urgency_confidence=0.75,
            t0=t0,
            suggested_tool="get_vision",
        )

    if _search(cleaned, _SPEAK_DIRECT_RE):
        return _build_decision(
            rule="speak_direct",
            text=text,
            target_module="speak",
            target_confidence=0.90,
            direct=True,
            direct_confidence=0.88,
            urgency=urgency,
            urgency_confidence=0.75,
            t0=t0,
            suggested_tool="speak",
        )

    affect = _detect_affect(cleaned)
    if affect:
        affect_choice, affect_conf, rule_name = affect
        return _build_decision(
            rule=rule_name,
            text=text,
            target_module="system2_chat",
            target_confidence=0.60,
            direct=False,
            direct_confidence=0.55,
            urgency=urgency,
            urgency_confidence=0.60,
            t0=t0,
            affect=affect_choice,
            affect_confidence=affect_conf,
        )

    if _search(cleaned, _CAMERA_SOFT_RE):
        return _build_decision(
            rule="camera_query_conversation",
            text=text,
            target_module="camera",
            target_confidence=0.78,
            direct=False,
            direct_confidence=0.80,
            urgency=urgency,
            urgency_confidence=0.70,
            t0=t0,
        )

    if _search(cleaned, _SPEAK_SOFT_RE):
        return _build_decision(
            rule="speak_query_conversation",
            text=text,
            target_module="speak",
            target_confidence=0.70,
            direct=False,
            direct_confidence=0.70,
            urgency=urgency,
            urgency_confidence=0.60,
            t0=t0,
        )

    return None


def _light_toggle_off(cleaned: str) -> bool:
    if _LIGHT_TOGGLE_OFF.search(cleaned) and _first_color(cleaned) is None:
        return True
    return False


def _build_light_decision(
    *,
    text: str,
    t0: float,
    urgency: float,
    color: str,
    effect: Optional[str],
    rule: str,
    action_proposal_cfg: Optional[Dict[str, Any]] = None,
) -> LayaDecision:
    decision = _build_decision(
        rule=rule,
        text=text,
        target_module="neopixel",
        target_confidence=0.94,
        direct=True,
        direct_confidence=0.93,
        urgency=urgency,
        urgency_confidence=0.70,
        t0=t0,
        suggested_tool="set_lights",
        extra_answers={
            "action_color": {"type": "choice", "choice": color, "confidence": 0.95},
            "action_effect": {
                "type": "choice",
                "choice": effect or _UNSPECIFIED,
                "confidence": 0.95 if effect else 0.50,
            },
        },
    )
    decision.suggested_action = build_laya_action_proposal(
        target_module=decision.target_module,
        module_confidence=decision.module_confidence,
        is_direct_command=decision.is_direct_command,
        direct_confidence=decision.direct_confidence,
        answers=decision.raw_answers,
        policy=action_proposal_cfg or {},
    )
    return decision


def _detect_affect(cleaned: str) -> Optional[Tuple[str, float, str]]:
    for affect_choice, patterns in _AFFECT_RE.items():
        hit = _search(cleaned, patterns)
        if hit:
            return affect_choice, 0.80, "affect_" + affect_choice
    return None


def _build_decision(
    *,
    rule: str,
    text: str,
    target_module: str,
    target_confidence: float,
    direct: bool,
    direct_confidence: float,
    urgency: float,
    urgency_confidence: float,
    t0: float,
    affect: Optional[str] = None,
    affect_confidence: float = 0.5,
    suggested_tool: Optional[str] = None,
    extra_answers: Optional[Dict[str, Any]] = None,
) -> LayaDecision:
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    raw_answers: Dict[str, Any] = {
        "backend": "rules",
        "rule": rule,
        "target_module": {
            "type": "choice",
            "choice": target_module,
            "confidence": target_confidence,
        },
        "is_direct_command": {
            "type": "choice",
            "choice": "direct_action" if direct else "conversation",
            "confidence": direct_confidence,
        },
    }
    if extra_answers:
        raw_answers.update(extra_answers)
    decision = LayaDecision(
        target_module=target_module,
        module_confidence=target_confidence,
        is_direct_command=direct,
        direct_confidence=direct_confidence,
        affective_event=affect or "neutral",
        affect_confidence=affect_confidence,
        urgency_score=float(urgency),
        urgency_confidence=float(urgency_confidence),
        inference_ms=elapsed_ms,
        suggested_tool=suggested_tool,
        raw_answers=raw_answers,
    )
    logger.debug(
        "rules decision: rule=%s target=%s direct=%s urgency=%.2f in %.2fms",
        rule,
        target_module,
        direct,
        urgency,
        elapsed_ms,
    )
    return decision


def urgency_bonus(text: str) -> float:
    return _urgency_bonus(text)


__all__ = [
    "classify",
    "is_conversational_query",
    "is_negated_command",
    "urgency_bonus",
]
