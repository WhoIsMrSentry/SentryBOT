from __future__ import annotations

import glob
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("agent.laya_engine")

THINKING_FILLERS_TR = [
    "Hemen bakıyorum...",
    "Bir düşüneyim...",
    "Hımm, anladım...",
    "Bakalım dostum...",
    "Hemen inceliyorum...",
]

THINKING_FILLERS_EN = [
    "Hmm, let me think...",
    "Looking into that...",
    "One second...",
    "Checking that for you...",
]

FAST_ACK_TR = [
    "Hemen yapıyorum!",
    "Tamamdır!",
    "Anlaşıldı!",
]

FAST_ACK_EN = [
    "On it!",
    "Right away!",
    "Got it!",
]


@dataclass
class LayaDecision:
    """Represents a single System 1 reflex decision from the Laya neural model."""

    target_module: str
    module_confidence: float
    is_direct_command: bool
    direct_confidence: float
    affective_event: str
    affect_confidence: float
    urgency_score: float
    urgency_confidence: float
    inference_ms: float
    suggested_tool: Optional[str] = None
    suggested_action: Optional[Dict[str, Any]] = None
    raw_answers: Dict[str, Any] = field(default_factory=dict)
    emergency_threshold: float = 2.0
    emergency_target_confidence_threshold: float = 0.90
    emergency_direct_confidence_threshold: float = 0.80
    emergency_urgency_confidence_threshold: float = 0.80

    @property
    def is_emergency(self) -> bool:
        direct_is_confident = (
            self.is_direct_command
            and self.direct_confidence >= self.emergency_direct_confidence_threshold
        )
        target_is_confident = (
            self.target_module == "emergency_stop"
            and self.module_confidence >= self.emergency_target_confidence_threshold
        )
        urgency_is_confident = (
            self.urgency_score >= self.emergency_threshold
            and self.urgency_confidence >= self.emergency_urgency_confidence_threshold
        )
        return direct_is_confident and (target_is_confident or urgency_is_confident)


class LayaEngine:
    """System 1 Reflex Engine powered by the Laya multilingual model.

    Provides sub-50ms neural intent routing, urgency scoring, affective event
    classification, and fast-path reflex execution without invoking heavy LLMs.
    """

    _instance: Optional["LayaEngine"] = None
    _lock = threading.Lock()

    # SentryBOT standard question specification for Laya System 1
    SENTRYBOT_QUESTIONS: Dict[str, Any] = {
        "target_module": {
            "type": "choice",
            "instructions": "Bu kullanıcı girdisi SentryBOT robotunun hangi donanım/eylem modülüne ait?",
            "criteria": {
                "neopixel": "Işık, renk, parlaklık veya LED animasyonlarını değiştirme",
                "arduino_serial": "Kafa hareketi, pan/tilt, motor, yürüme veya durdurma",
                "emergency_stop": "Acil durum, anında durma, tehlike, çarpma riski veya acil kapatma",
                "speak": "Robotun bir şey söylemesini, konuşmasını veya ses çıkarmasını isteme",
                "camera": "Kamera, görme, etrafa bakma, nesne/yüz tanıma veya görsel soru",
                "system2_chat": "Genel sohbet, soru-cevap, felsefe, akıl yürütme, hikaye veya tavsiye",
            },
        },
        "is_direct_command": {
            "type": "choice",
            "instructions": "Bu girdi doğrudan hızlı icra edilecek bir donanım komutu mu yoksa düşünce gerektiren sohbet mi?",
            "criteria": {
                "direct_action": "Hemen uygulanacak net bir donanım/refleks komutu",
                "conversation": "Düşünce, cevap veya diyalog gerektiren sohbet/soru",
            },
        },
        "affective_event": {
            "type": "choice",
            "instructions": "Kullanıcının robota karşı duygusal/sosyal tutumu nedir?",
            "criteria": {
                "user_praise": "Övgü, sevgi, aferin, teşekkür, iltifat veya sevme",
                "user_rude": "Kabalık, hakaret, küfür, susturma veya kızgınlık",
                "neutral": "Duygusal olmayan nötr komut veya bilgi sorusu",
            },
        },
        "urgency": {
            "type": "score",
            "instructions": "Bu girdinin aciliyet ve tehlike seviyesi nedir?",
            "criteria": [
                "sakin, normal konuşma veya bilgi sorusu",
                "normal günlük hareket veya rutin eylem komutu",
                "hızlı yapılması istenen öncelikli komut",
                "son derece acil, tehlike, kaza riski veya anında durdurma",
            ],
        },
    }

    MODULE_TOOL_MAP: Dict[str, str] = {
        "neopixel": "set_lights",
        "arduino_serial": "move_head",
        "emergency_stop": "stop_follow",
        "speak": "speak",
        "camera": "get_vision",
    }

    def __init__(
        self,
        enabled: bool = True,
        confidence_threshold: float = 0.60,
        model_name_or_path: Optional[str] = None,
        subfolder: str = "multilingual",
        device: str = "cpu",
        laya_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.enabled = enabled
        self.confidence_threshold = float(confidence_threshold)
        self.subfolder = subfolder
        self.device = device
        self._model_path = model_name_or_path
        self._agent: Any = None
        self._load_lock = threading.Lock()
        self._load_attempted = False
        self._is_available = False
        self._load_time_ms = 0.0

        # Config-driven sub-sections
        _cfg = laya_cfg or {}
        fast_cfg = _cfg.get("fast_path", {}) if isinstance(_cfg.get("fast_path"), dict) else {}
        self.fast_path_enabled = bool(fast_cfg.get("enabled", True))
        self.emergency_bypass_safety = bool(fast_cfg.get("emergency_bypass_safety", False))

        filler_cfg = _cfg.get("filler", {}) if isinstance(_cfg.get("filler"), dict) else {}
        self.filler_enabled = bool(filler_cfg.get("enabled", True))
        self.filler_cooldown_s = float(filler_cfg.get("cooldown_s", 12.0))
        self.filler_mood_aware = bool(filler_cfg.get("mood_aware", True))
        self._last_filler_ts = 0.0

        affect_cfg = _cfg.get("affective", {}) if isinstance(_cfg.get("affective"), dict) else {}
        self.mood_impact_scale = float(affect_cfg.get("mood_impact_scale", 1.0))
        self.vision_events_enabled = bool(affect_cfg.get("vision_events", True))
        self.face_emotion_events_enabled = bool(affect_cfg.get("face_emotion_events", True))

        urgency_cfg = _cfg.get("urgency", {}) if isinstance(_cfg.get("urgency"), dict) else {}
        self.emergency_threshold = float(urgency_cfg.get("emergency_threshold", 2.0))
        self.high_urgency_threshold = float(urgency_cfg.get("high_threshold", 1.5))
        self.high_urgency_confidence_threshold = float(urgency_cfg.get("high_confidence_threshold", 0.60))
        self.emergency_target_confidence_threshold = float(
            urgency_cfg.get("emergency_target_confidence_threshold", 0.90)
        )
        self.emergency_direct_confidence_threshold = float(
            urgency_cfg.get("emergency_direct_confidence_threshold", 0.80)
        )
        self.emergency_urgency_confidence_threshold = float(
            urgency_cfg.get("emergency_urgency_confidence_threshold", 0.80)
        )
        self.sensor_boost_hz = float(urgency_cfg.get("sensor_boost_hz", 5.0))
        self.sensor_boost_hold_s = float(urgency_cfg.get("sensor_boost_hold_s", 8.0))

        action_cfg = _cfg.get("action_proposals", {})
        self.action_proposal_cfg = action_cfg if isinstance(action_cfg, dict) else {}

        telem_cfg = _cfg.get("telemetry", {}) if isinstance(_cfg.get("telemetry"), dict) else {}
        self._log_decisions = bool(telem_cfg.get("log_decisions", True))
        self._max_decision_log = int(telem_cfg.get("max_decision_log", 20))

        # Telemetry counters
        self._decision_count = 0
        self._total_inference_ms = 0.0
        self._last_decisions: List[Dict[str, Any]] = []
        self._last_decision: Optional["LayaDecision"] = None

    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> "LayaEngine":
        """Thread-safe singleton accessor."""
        with cls._lock:
            if cls._instance is None:
                cfg = config or {}
                tri_cfg = cfg.get("tri_layer", {}) if isinstance(cfg.get("tri_layer"), dict) else {}
                laya_cfg = tri_cfg.get("laya", {}) if isinstance(tri_cfg.get("laya"), dict) else {}
                enabled = bool(laya_cfg.get("enabled", True))
                threshold = float(laya_cfg.get("confidence_threshold", 0.60))
                model_path = laya_cfg.get("model_path")
                device = str(laya_cfg.get("device", "cpu"))
                cls._instance = cls(
                    enabled=enabled,
                    confidence_threshold=threshold,
                    model_name_or_path=model_path,
                    device=device,
                    laya_cfg=laya_cfg,
                )
            return cls._instance

    @staticmethod
    def _find_cached_snapshot() -> Optional[str]:
        """Locates pre-downloaded Hugging Face snapshot for convaiinnovations/laya."""
        hub_pattern = os.path.expanduser(
            "~/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/*/multilingual"
        )
        matches = glob.glob(hub_pattern)
        if matches and os.path.isdir(matches[0]):
            return matches[0]

        parent_pattern = os.path.expanduser(
            "~/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/*"
        )
        parent_matches = glob.glob(parent_pattern)
        for snapshot in parent_matches:
            if os.path.isdir(snapshot):
                multi = os.path.join(snapshot, "multilingual")
                if os.path.isdir(multi):
                    return multi
                if os.path.isfile(os.path.join(snapshot, "model.safetensors")):
                    return snapshot
        return None

    def _ensure_loaded(self) -> bool:
        """Lazily loads the Laya model on first inference request."""
        if not self.enabled:
            return False
        if self._is_available and self._agent is not None:
            return True
        if self._load_attempted and not self._is_available:
            return False

        with self._load_lock:
            if self._agent is not None:
                return True
            self._load_attempted = True
            try:
                import laya  # type: ignore
            except ImportError:
                logger.warning(
                    "laya library is not installed in current environment. "
                    "System 1 neural reflexes will use fallback routing."
                )
                self._is_available = False
                return False

            t0 = time.perf_counter()
            resolved_path = self._model_path or self._find_cached_snapshot()
            try:
                if resolved_path and os.path.exists(resolved_path):
                    logger.info("Loading Laya model from local snapshot: %s", resolved_path)
                    self._agent = laya.load(resolved_path)
                else:
                    logger.info("Loading Laya model from HF hub: convaiinnovations/laya (subfolder=%s)", self.subfolder)
                    self._agent = laya.load("convaiinnovations/laya", subfolder=self.subfolder)

                self._load_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                self._is_available = True
                logger.info(
                    "Laya System 1 loaded successfully in %.2f ms (device=%s)",
                    self._load_time_ms,
                    getattr(self._agent, "device", "unknown"),
                )
                return True
            except Exception as exc:
                logger.warning("Failed to initialize Laya model: %s", exc)
                self._is_available = False
                return False

    @property
    def is_available(self) -> bool:
        return self._is_available or (self.enabled and not self._load_attempted)

    def decide(self, text: str) -> Optional[LayaDecision]:
        """Runs fast System 1 inference on user input."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return None

        if not self._ensure_loaded() or self._agent is None:
            return None

        t0 = time.perf_counter()
        try:
            state = {"text": cleaned}
            questions = self.SENTRYBOT_QUESTIONS
            if self.action_proposal_cfg.get("enabled", False):
                from modules.agent_core.services.laya_action_contract import get_laya_action_questions

                questions = {**questions, **get_laya_action_questions()}
            raw = self._agent.system_one(state, questions)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            answers = raw.get("answers", {}) if isinstance(raw, dict) else {}

            target_ans = answers.get("target_module", {})
            target_mod = str(target_ans.get("choice") or target_ans.get("value") or "system2_chat")
            target_conf = float(target_ans.get("confidence", 0.0))

            direct_ans = answers.get("is_direct_command", {})
            direct_choice = str(direct_ans.get("choice") or direct_ans.get("value") or "conversation")
            direct_conf = float(direct_ans.get("confidence", 0.0))
            is_direct = direct_choice == "direct_action"

            affect_ans = answers.get("affective_event", {})
            affect_choice = str(affect_ans.get("choice") or affect_ans.get("value") or "neutral")
            affect_conf = float(affect_ans.get("confidence", 0.0))

            urgency_ans = answers.get("urgency", {})
            urgency_score = float(urgency_ans.get("score") if "score" in urgency_ans else urgency_ans.get("value", 0.0))
            urgency_conf = float(urgency_ans.get("confidence", 0.0))

            suggested_tool = self.MODULE_TOOL_MAP.get(target_mod)

            decision = LayaDecision(
                target_module=target_mod,
                module_confidence=target_conf,
                is_direct_command=is_direct,
                direct_confidence=direct_conf,
                affective_event=affect_choice,
                affect_confidence=affect_conf,
                urgency_score=urgency_score,
                urgency_confidence=urgency_conf,
                inference_ms=elapsed_ms,
                suggested_tool=suggested_tool,
                raw_answers=answers,
                emergency_threshold=self.emergency_threshold,
                emergency_target_confidence_threshold=self.emergency_target_confidence_threshold,
                emergency_direct_confidence_threshold=self.emergency_direct_confidence_threshold,
                emergency_urgency_confidence_threshold=self.emergency_urgency_confidence_threshold,
            )
            if self.action_proposal_cfg.get("enabled", False):
                from modules.agent_core.services.laya_action_contract import build_laya_action_proposal

                decision.suggested_action = build_laya_action_proposal(
                    target_module=target_mod,
                    module_confidence=target_conf,
                    is_direct_command=is_direct,
                    direct_confidence=direct_conf,
                    answers=answers,
                    policy=self.action_proposal_cfg,
                )

            # Telemetry tracking
            self._decision_count += 1
            self._total_inference_ms += elapsed_ms
            self._last_decision = decision
            if self._log_decisions:
                self._last_decisions.append({
                    "text": cleaned[:50],
                    "target": target_mod,
                    "conf": round(target_conf, 3),
                    "direct": is_direct,
                    "affect": affect_choice,
                    "urgency": round(urgency_score, 2),
                    "ms": elapsed_ms,
                    "timestamp": time.time(),
                })
                if len(self._last_decisions) > self._max_decision_log:
                    self._last_decisions = self._last_decisions[-self._max_decision_log:]
                logger.debug(
                    "Laya decision: target=%s conf=%.2f direct=%s affect=%s urgency=%.1f in %.1fms",
                    target_mod, target_conf, is_direct, affect_choice, urgency_score, elapsed_ms,
                )

            return decision
        except Exception as exc:
            logger.warning("Laya inference failed for text '%s': %s", cleaned[:50], exc)
            return None

    def route(self, user_prompt: str, available_modules: Sequence[str]) -> List[str]:
        """Provides Laya-enhanced module routing.

        Returns prioritized list of modules based on System 1 neural classification.
        """
        decision = self.decide(user_prompt)
        if decision is None:
            return []

        if decision.module_confidence < self.confidence_threshold:
            return []

        target = decision.target_module
        if target in available_modules:
            return [target]

        # Aliases mapping
        alias_map = {
            "emergency_stop": ["arduino_serial", "autonomy"],
            "camera": ["vlm_bridge", "camera"],
            "speak": ["speak"],
            "neopixel": ["neopixel", "interactions"],
            "arduino_serial": ["arduino_serial", "hardware"],
            "system2_chat": ["autonomy", "agent_core"],
        }
        candidates = alias_map.get(target, [])
        return [c for c in candidates if c in available_modules]

    def should_fast_path(
        self,
        user_prompt: str,
        world_state: Optional[Dict[str, Any]] = None,
        visual_context: Optional[str] = None,
    ) -> Tuple[bool, Optional["LayaDecision"]]:
        """Determines if the prompt qualifies for instant hardware fast-path execution."""
        if not self.fast_path_enabled:
            return False, None

        decision = self.decide_with_context(
            user_prompt,
            world_state=world_state,
            visual_context=visual_context,
        )
        if decision is None:
            return False, None

        if decision.is_emergency:
            return True, decision

        if decision.urgency_score >= self.high_urgency_threshold:
            if decision.is_direct_command and decision.direct_confidence >= self.confidence_threshold:
                return True, decision

        if decision.is_direct_command and decision.direct_confidence >= self.confidence_threshold:
            if decision.target_module in {"neopixel", "arduino_serial", "speak", "emergency_stop"}:
                return True, decision

        return False, decision

    def decide_with_context(
        self,
        text: str,
        world_state: Optional[Dict[str, Any]] = None,
        visual_context: Optional[str] = None,
    ) -> Optional["LayaDecision"]:
        """Context-enriched System 1 decision.

        Enriches the raw text with visual scene context and adjusts urgency
        based on world state (battery, temperature, follow mode).
        """
        enriched = str(text or "").strip()
        if not enriched:
            return None

        if visual_context:
            scene_hint = str(visual_context)[:100]
            enriched = f"{enriched} [Sahne: {scene_hint}]"

        decision = self.decide(enriched)
        if decision is None:
            return None

        # World state adjustments
        if isinstance(world_state, dict):
            battery = world_state.get("battery_percent", 100)
            try:
                bat_val = float(battery)
            except (TypeError, ValueError):
                bat_val = 100.0
            if bat_val < 15 and decision.urgency_score < self.high_urgency_threshold:
                decision.urgency_score = self.high_urgency_threshold

            follow_active = world_state.get("follow_active", False)
            if follow_active and decision.target_module == "camera":
                decision.module_confidence = min(1.0, decision.module_confidence + 0.15)

        return decision

    def is_urgent(self, decision: Optional["LayaDecision"] = None) -> bool:
        """Check if the latest or given decision indicates high urgency."""
        dec = decision or self._last_decision
        if dec is None:
            return False
        return bool(getattr(dec, "is_emergency", False)) or (
            dec.urgency_score >= self.high_urgency_threshold
            and dec.urgency_confidence >= self.high_urgency_confidence_threshold
        )

    def is_emergency_decision(self, decision: Optional["LayaDecision"] = None) -> bool:
        """Check if the latest or given decision is an emergency."""
        dec = decision or self._last_decision
        if dec is None:
            return False
        return bool(getattr(dec, "is_emergency", False))

    def get_instant_filler(self, language: str = "tr") -> str:
        """Returns an immediate conversational thinking filler (<100ms backchannel)."""
        if not self.filler_enabled:
            return ""
        now = time.time()
        if now - self._last_filler_ts < self.filler_cooldown_s:
            return ""
        self._last_filler_ts = now
        lang = str(language or "tr").lower()
        if lang.startswith("en"):
            return random.choice(THINKING_FILLERS_EN)
        return random.choice(THINKING_FILLERS_TR)

    def get_filler_with_affect(self, language: str = "tr", mood: str = "neutral") -> str:
        """Mood-aware thinking filler — adjusts tone based on current emotion."""
        if not self.filler_enabled:
            return ""
        now = time.time()
        if now - self._last_filler_ts < self.filler_cooldown_s:
            return ""
        self._last_filler_ts = now

        if not self.filler_mood_aware or mood == "neutral":
            return self.get_instant_filler.__wrapped__(self, language) if hasattr(self.get_instant_filler, '__wrapped__') else self._pick_filler(language)

        lang = str(language or "tr").lower()
        is_en = lang.startswith("en")

        if mood in ("joy", "curiosity"):
            pool = [
                "Oh, interesting!", "Let me check!", "Curious about that...",
            ] if is_en else [
                "Hemen bakıyorum!", "Ooo, ilginç bir soru!", "Bakalım ne bulacağım...",
            ]
        elif mood in ("sadness", "tired"):
            pool = [
                "Let me see...", "Thinking...", "Hmm...",
            ] if is_en else [
                "Hmm, bakayım...", "Bir kontrol edeyim...", "Düşünüyorum...",
            ]
        elif mood in ("anger", "furious"):
            pool = [
                "Fine, checking.", "One moment.", "Looking into it.",
            ] if is_en else [
                "Tamam, hemen bakıyorum.", "Bir dakika.", "İnceliyorum.",
            ]
        elif mood in ("fear",):
            pool = [
                "O-okay, let me check...", "Hmm, checking...",
            ] if is_en else [
                "T-tamam, bakıyorum...", "Hemen kontrol ediyorum...",
            ]
        else:
            pool = THINKING_FILLERS_EN if is_en else THINKING_FILLERS_TR

        return random.choice(pool)

    def _pick_filler(self, language: str = "tr") -> str:
        """Raw filler pick without cooldown check (internal use)."""
        lang = str(language or "tr").lower()
        if lang.startswith("en"):
            return random.choice(THINKING_FILLERS_EN)
        return random.choice(THINKING_FILLERS_TR)

    def get_fast_ack(self, language: str = "tr") -> str:
        """Returns an instant verbal acknowledgment for direct actions."""
        lang = str(language or "tr").lower()
        if lang.startswith("en"):
            return random.choice(FAST_ACK_EN)
        return random.choice(FAST_ACK_TR)

    def get_affective_reaction(self, affect: str) -> Dict[str, Any]:
        """Maps detected affective event to immediate OLED face, LED, and emotion."""
        reactions: Dict[str, Dict[str, Any]] = {
            "user_praise": {
                "face": "happy",
                "emotion": "joy",
                "oled_text": "^_^",
                "led_color": "#00ff88",
                "led_mode": "pulse",
                "body_pose": {"pan_delta": 5, "tilt_delta": -3},
            },
            "user_rude": {
                "face": "sad",
                "emotion": "sorrow",
                "oled_text": ":'(",
                "led_color": "#ff3333",
                "led_mode": "slow_breathe",
                "body_pose": {"pan_delta": -3, "tilt_delta": 5},
            },
        }
        if affect in reactions:
            return dict(reactions[affect])
        return {
            "face": "neutral",
            "emotion": "neutral",
            "oled_text": "-_-",
            "led_color": "#00d4ff",
            "led_mode": "static",
            "body_pose": {"pan_delta": 0, "tilt_delta": 0},
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns Laya System 1 performance telemetry and decision history."""
        avg_ms = (
            round(self._total_inference_ms / self._decision_count, 2)
            if self._decision_count > 0
            else 0.0
        )
        return {
            "available": self._is_available,
            "enabled": self.enabled,
            "fast_path_enabled": self.fast_path_enabled,
            "filler_enabled": self.filler_enabled,
            "confidence_threshold": self.confidence_threshold,
            "emergency_threshold": self.emergency_threshold,
            "high_urgency_threshold": self.high_urgency_threshold,
            "high_urgency_confidence_threshold": self.high_urgency_confidence_threshold,
            "emergency_target_confidence_threshold": self.emergency_target_confidence_threshold,
            "emergency_direct_confidence_threshold": self.emergency_direct_confidence_threshold,
            "emergency_urgency_confidence_threshold": self.emergency_urgency_confidence_threshold,
            "decision_count": self._decision_count,
            "avg_inference_ms": avg_ms,
            "load_time_ms": self._load_time_ms,
            "last_decisions": list(self._last_decisions[-5:]),
            "last_target": self._last_decision.target_module if self._last_decision else None,
            "last_urgency": self._last_decision.urgency_score if self._last_decision else None,
        }

    def get_mood_deltas(self, decision: Optional["LayaDecision"] = None) -> Dict[str, float]:
        """Compute mood state deltas from a Laya decision, scaled by mood_impact_scale.

        Returns a dict of {mood_axis: delta} suitable for MoodManager.modify().
        """
        dec = decision or self._last_decision
        if dec is None:
            return {}

        scale = self.mood_impact_scale
        deltas: Dict[str, float] = {}

        if dec.affective_event == "user_praise":
            deltas["happiness"] = 25.0 * scale
            deltas["anger"] = -15.0 * scale
        elif dec.affective_event == "user_rude":
            deltas["anger"] = 30.0 * scale
            deltas["happiness"] = -25.0 * scale
            deltas["fear"] = 10.0 * scale

        if bool(getattr(dec, "is_emergency", False)):
            deltas["fear"] = deltas.get("fear", 0.0) + 20.0 * scale
            deltas["energy"] = deltas.get("energy", 0.0) - 10.0 * scale
        elif (
            dec.urgency_score >= self.high_urgency_threshold
            and dec.urgency_confidence >= self.high_urgency_confidence_threshold
        ):
            deltas["curiosity"] = deltas.get("curiosity", 0.0) + 10.0 * scale

        if dec.is_direct_command:
            deltas["stimulation_satisfy"] = 15.0 * scale

        if dec.target_module == "system2_chat":
            deltas["social_satisfy"] = 20.0 * scale

        return deltas
