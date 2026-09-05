from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time
from typing import Any, Dict, Optional

from .affective_appraisal import AffectiveAppraisal
from .audio_event_needs_bridge import AudioEventNeedsBridge
from .barge_in import BargeInController
from .behavior_shadow_learner import BehaviorShadowLearner
from .client import ServiceClient
from .companion_auto_execute_gate import CompanionAutoExecuteGate
from .companion_goal_executor import CompanionGoalExecutor
from .companion_goal_selector import CompanionGoalSelector
from .companion_lines import CompanionLineGenerator
from .companion_rituals import CompanionRituals
from .expression_director import ExpressionDirector
from .hardware_policy import apply_runtime_hardware_policy
from .interaction_feedback import InteractionFeedbackLearner
from .liveliness import LivelinessScheduler
from .living_needs import LivingNeedsEngine
from .memory import ShortTermMemory
from .memory_decision_shadow import MemoryDecisionShadow
from .memory_needs_bias import MemoryNeedsBias
from .mood import MoodManager
from .needs_engine import CompanionNeedsEngine
from .proactive_planner import ProactivePlanner
from .reflection_planner import ReflectionPlanner
from modules.cognitive_memory.services.relationship_memory import RelationshipMemory
from .safe_navigation import SafeNavigationMemory
from .spinal_cord_reflex import SpinalCordReflexEngine
from .vision_context_needs_bridge import VisionContextNeedsBridge
from modules.cognitive_memory.services.world_memory_autowriter import WorldMemoryAutoWriter
from modules.cognitive_memory.services.world_memory_rag import WorldMemoryRAG as WorldMemory
from .behavior_composer import BehaviorComposer
from .scene_register import SceneRegister

logger = logging.getLogger("autonomy.brain_init")


class BrainInitMixin:
    """Initializes components, background workers, and state models for AutonomyBrain."""

    def _init_components(self, config: dict[str, Any]) -> None:
        self.config = config
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._agentic_decision_in_progress: bool = False
        self._agentic_decision_lock = threading.Lock()
        self._worker_executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="autonomy_worker"
        )

        self.mood = MoodManager(config)
        self.appraisal = AffectiveAppraisal(config)
        self.client = ServiceClient(config.get("endpoints", {}), config=config)
        self.expression = ExpressionDirector(self.client)
        self.memory = ShortTermMemory(max_items=20)
        companion_cfg = config.get("companion", {}) if isinstance(config.get("companion", {}), dict) else {}
        self.relationship_memory = RelationshipMemory(
            enabled=bool(companion_cfg.get("enabled", True)),
            path=str(companion_cfg.get("relationship_memory_path", "modules/autonomy/data/relationship_memory.json")),
        )
        self.companion_rituals = CompanionRituals(
            companion_cfg.get("rituals", {}) if isinstance(companion_cfg.get("rituals", {}), dict) else {}
        )
        lines_cfg = companion_cfg.get("lines", {}) if isinstance(companion_cfg.get("lines", {}), dict) else {}
        self.companion_lines = CompanionLineGenerator(self.client, lines_cfg)
        self.proactive_planner = ProactivePlanner(
            companion_cfg.get("proactive", {}) if isinstance(companion_cfg.get("proactive", {}), dict) else {},
            line_generator=self.companion_lines,
        )
        learning_cfg = (
            companion_cfg.get("learning", {}) if isinstance(companion_cfg.get("learning", {}), dict) else {}
        )
        self.feedback_learner = InteractionFeedbackLearner(learning_cfg.get("feedback", learning_cfg))
        needs_cfg = (
            self.config.get("companion_needs", {})
            if isinstance(self.config.get("companion_needs", {}), dict)
            else {}
        )
        self.needs_engine = CompanionNeedsEngine(needs_cfg)
        goal_cfg = (
            self.config.get("companion_goals", {})
            if isinstance(self.config.get("companion_goals", {}), dict)
            else {}
        )
        self.goal_selector = CompanionGoalSelector(goal_cfg)
        executor_cfg = (
            self.config.get("companion_goal_executor", {})
            if isinstance(self.config.get("companion_goal_executor", {}), dict)
            else {}
        )
        self.goal_executor = CompanionGoalExecutor(
            apply_runtime_hardware_policy(executor_cfg),
            client=self.client,
        )
        auto_exec_cfg = (
            self.config.get("companion_auto_execute", {})
            if isinstance(self.config.get("companion_auto_execute", {}), dict)
            else {}
        )
        self.goal_auto_execute_gate = CompanionAutoExecuteGate(
            apply_runtime_hardware_policy(auto_exec_cfg)
        )
        self.reflection_planner = ReflectionPlanner(config)
        vision_needs_cfg = (
            self.config.get("vision_context_needs", {})
            if isinstance(self.config.get("vision_context_needs", {}), dict)
            else {}
        )
        self.vision_context_needs_bridge = VisionContextNeedsBridge(vision_needs_cfg)
        audio_needs_cfg = (
            self.config.get("audio_event_needs", {})
            if isinstance(self.config.get("audio_event_needs", {}), dict)
            else {}
        )
        self.audio_event_needs_bridge = AudioEventNeedsBridge(audio_needs_cfg)
        world_memory_cfg = (
            self.config.get("world_memory", {})
            if isinstance(self.config.get("world_memory", {}), dict)
            else {}
        )
        self.world_memory = WorldMemory(world_memory_cfg)
        living_needs_cfg = (
            self.config.get("living_needs", {})
            if isinstance(self.config.get("living_needs", {}), dict)
            else {}
        )
        self.living_needs = LivingNeedsEngine(living_needs_cfg)
        safe_navigation_cfg = (
            self.config.get("safe_navigation", {})
            if isinstance(self.config.get("safe_navigation", {}), dict)
            else {}
        )
        self.safe_navigation = SafeNavigationMemory(safe_navigation_cfg, client=self.client)
        memory_decision_cfg = (
            self.config.get("memory_decision_shadow", {})
            if isinstance(self.config.get("memory_decision_shadow", {}), dict)
            else {}
        )
        self.memory_decision_shadow = MemoryDecisionShadow(memory_decision_cfg)
        memory_bias_cfg = (
            self.config.get("memory_needs_bias", {})
            if isinstance(self.config.get("memory_needs_bias", {}), dict)
            else {}
        )
        self.memory_needs_bias = MemoryNeedsBias(memory_bias_cfg)
        world_memory_autowrite_cfg = (
            self.config.get("world_memory_autowrite", {})
            if isinstance(self.config.get("world_memory_autowrite", {}), dict)
            else {}
        )
        self.world_memory_autowriter = WorldMemoryAutoWriter(world_memory_autowrite_cfg)
        self.barge_in = BargeInController(
            config.get("barge_in", {}) if isinstance(config.get("barge_in", {}), dict) else {}
        )
        self.liveliness = LivelinessScheduler(
            config.get("liveliness", {}) if isinstance(config.get("liveliness", {}), dict) else {}
        )
        self._vision_cfg = config.get("vision_hooks", {})
        self.owner_cfg = config.get("owner", {})

        spinal_cfg = (
            self.config.get("spinal_cord", {})
            if isinstance(self.config.get("spinal_cord", {}), dict)
            else {}
        )
        self.spinal_cord = SpinalCordReflexEngine(spinal_cfg, client=self.client, memory=self.memory)

        shadow_cfg = (
            self.config.get("shadow_learner", {})
            if isinstance(self.config.get("shadow_learner", {}), dict)
            else {}
        )
        self.shadow_learner = BehaviorShadowLearner(shadow_cfg)
        # C4: shared write lock serializing side-thread memory writes
        # (ritual reflection) against the brain dream-cycle prune/consolidate.
        self._memory_write_lock = threading.Lock()

        # Peripheral Vision L1 & Behavior Composer
        scene_cfg = self.config.get("scene_register", {}) if isinstance(self.config.get("scene_register"), dict) else {}
        self.scene_register = SceneRegister(window_s=float(scene_cfg.get("window_s", 5.0)))
        self.behavior_composer = BehaviorComposer(brain=self, client=self.client)

        self._init_agent_core()
        self._init_state()

    def _init_agent_core(self) -> None:
        self.agent = None
        try:
            from modules.agent_core.services.agent import AgentOrchestrator  # type: ignore
            from modules.agent_core.config_loader import load_config as load_agent_core_config  # type: ignore

            agent_cfg = load_agent_core_config()
            self.agent = AgentOrchestrator(agent_cfg, autonomy_client=self.client)
            llm_cfg = agent_cfg.get("llm", {}) if isinstance(agent_cfg.get("llm", {}), dict) else {}
            provider = str(llm_cfg.get("provider", "ollama"))
            model = str(agent_cfg.get("agent", {}).get("model", ""))
            logger.info("Agent Core integrated successfully (provider=%s model=%s).", provider, model)
        except Exception as exc:
            logger.warning("Agent Core init skipped/failed (non-fatal): %s", exc)

    def _init_state(self) -> None:
        self.state = {
            "last_interaction": time.time(),
            "is_bored": False,
            "is_sleeping": False,
            "last_speech_text": "",
            "last_speech_time": 0,
            "last_speech_language": "tr",
            "current_pan": 90,
            "current_tilt": 90,
            "last_emotion": None,
            "last_vision_poll": 0.0,
            "owner_last_seen": 0.0,
            "owner_lockout_until": 0.0,
            "owner_last_greet": 0.0,
            "rfid_authorized_until": 0.0,
            "last_speaker": None,
            "persona_mode": None,
            "companion_needs": {},
            "companion_behavior_history": [],
            "vision_context_needs": {},
            "vision_context_history": [],
            "audio_event_needs": {},
            "audio_event_history": [],
            "world_memory": {},
            "world_memory_history": [],
            "memory_decision_shadow": {},
            "memory_needs_bias": {},
            "world_memory_autowrite": {},
            "world_memory_autowrite_history": [],
            "living_needs": {},
            "living_needs_history": [],
            "safe_navigation": {},
            "sound_interrupt": {},
            "sound_interrupt_history": [],
        }
        self._people_last_seen = {}
        self._last_emotion_sent = None
        self._current_people = {}
        self._attempt_log = []
        self._owner_report_pending = False
        self._llm_rate_limit_until = 0.0
        self._last_owner_scan = 0.0
        self._last_idle_action = 0.0
        self._last_agentic_ts = 0.0
        self._last_alone_appraisal_ts = 0.0
        self._last_darkness_appraisal_ts = 0.0
        self._last_owner_left_appraisal_ts = 0.0
        self._owner_was_present = False
        self._owner_session_id: int | None = None
        self._reset_daily_timeline()
        self._speech_req_lock = threading.Lock()
        self._active_speech_req_id: str = ""
        self._speech_busy: bool = False
        self._speech_min_interval_s = float(
            self.config.get("request_timeouts", {}).get("speech_min_interval_s", 0.35)
        )
        visuals_cfg = (
            self.config.get("visual_state", {})
            if isinstance(self.config.get("visual_state", {}), dict)
            else {}
        )
        self._visual_emotion_min_interval_s = float(visuals_cfg.get("emotion_min_interval_s", 2.0))
        self._visual_lock_default_s = float(visuals_cfg.get("default_lock_s", 2.2))
        self._visual_lock_strong_s = float(visuals_cfg.get("strong_lock_s", 4.5))
        self._visual_state_hold_s = float(visuals_cfg.get("state_hold_s", 3.0))
        self._visual_strong_emotions = {
            str(x).strip().lower()
            for x in (visuals_cfg.get("strong_emotions", ["fear", "angry", "furious"]) or [])
            if str(x).strip()
        }
        graph_cfg = (
            visuals_cfg.get("transition_graph", {})
            if isinstance(visuals_cfg.get("transition_graph", {}), dict)
            else {}
        )
        self._visual_transition_graph = {
            str(src).strip().lower(): [
                str(dst).strip().lower()
                for dst in (targets if isinstance(targets, list) else [])
                if str(dst).strip()
            ]
            for src, targets in graph_cfg.items()
            if str(src).strip()
        }
        self._last_emotion_sync_ts: float = 0.0
        # C3: express/visual-state fields are touched from the brain loop,
        # HTTP /express routes and agentic worker threads — one RLock guards
        # all of them.
        self._express_lock = threading.RLock()
        self._visual_lock_until: float = 0.0
        self._visual_lock_reason: str = ""
        self._visual_state_emotion: str = "neutral"
        self._visual_state_since: float = time.time()
