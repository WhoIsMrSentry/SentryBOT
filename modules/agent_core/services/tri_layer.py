from __future__ import annotations
import os as _sentrybot_env_os

def _sentrybot_agent_ollama_host() -> str:
    return (
        _sentrybot_env_os.environ.get("OLLAMA_HOST")
        or _sentrybot_env_os.environ.get("SENTRYBOT_OLLAMA_BASE_URL")
        or _sentrybot_env_os.environ.get("SENTRYBOT_REMOTE_OLLAMA_URL")
        or _sentrybot_env_os.environ.get("SENTRYBOT_OLLAMA_URL")
        or "http://whoismrsentry.local:11434"
    ).rstrip("/")

def _sentrybot_force_agent_ollama_env() -> None:
    host = _sentrybot_agent_ollama_host()
    _sentrybot_env_os.environ["OLLAMA_HOST"] = host
    _sentrybot_env_os.environ["OLLAMA_BASE_URL"] = host
    _sentrybot_env_os.environ.setdefault("SENTRYBOT_OLLAMA_BASE_URL", host)
    _sentrybot_env_os.environ.setdefault("SENTRYBOT_REMOTE_OLLAMA_URL", host)
    _sentrybot_env_os.environ.setdefault("SENTRYBOT_OLLAMA_URL", host)

_sentrybot_force_agent_ollama_env()


from dataclasses import dataclass
from typing import Dict, List, Sequence
import re


@dataclass(frozen=True)
class SubAgentProfile:
    module: str
    role: str
    goal: str
    allowed_tools: Sequence[str]
    keywords: Sequence[str]

# Compatibility fallback: older profiles may not define system_prompt.
def _subagent_profile_system_prompt(self):
    for attr in ("prompt", "instructions", "description", "role", "module"):
        value = getattr(self, attr, None)
        if value:
            return str(value)
    name = getattr(self, "name", self.__class__.__name__)
    return f"You are {name}, a SentryBOT sub-agent. Use available tools safely and briefly."

if not hasattr(SubAgentProfile, "system_prompt"):
    SubAgentProfile.system_prompt = property(_subagent_profile_system_prompt)


# Compatibility fallback: older profiles may not define name.
def _subagent_profile_name(self):
    for attr in ("id", "profile_id", "module", "role"):
        value = getattr(self, attr, None)
        if value:
            return str(value)
    return self.__class__.__name__

if not hasattr(SubAgentProfile, "name"):
    SubAgentProfile.name = property(_subagent_profile_name)


# Compatibility fallback: older profiles may not define enabled.
SubAgentProfile.enabled = True


def build_subagent_profiles(overrides: Dict[str, dict] | None = None) -> Dict[str, SubAgentProfile]:
    """Build default module-level sub-agent profiles with optional overrides."""
    profiles: Dict[str, SubAgentProfile] = {
        "agent_core": SubAgentProfile(
            module="agent_core",
            role="Core planner",
            goal="Coordinate safe planning and tool usage.",
            allowed_tools=(
                "search_memory",
                "get_sensor_data",
                "get_location",
                "pathfind",
                "list_locations",
                "update_location",
                "connect_locations",
            ),
            keywords=("plan", "reason", "agent", "cognitive", "strategy", "task"),
        ),
        "animate": SubAgentProfile(
            module="animate",
            role="Animation specialist",
            goal="Control expressive movement and animation cues.",
            allowed_tools=("interaction_event", "set_lights", "oled_face"),
            keywords=("animation", "animate", "gesture", "move style"),
        ),
        "arduino_serial": SubAgentProfile(
            module="arduino_serial",
            role="Serial hardware specialist",
            goal="Handle safe low-level hardware interactions.",
            allowed_tools=("move_head", "get_sensor_data"),
            keywords=("arduino", "serial", "servo", "motor", "laser"),
        ),
        "autonomy": SubAgentProfile(
            module="autonomy",
            role="Behavior specialist",
            goal="Decide autonomous behavior policy and perform expressive actions.",
            allowed_tools=(
                "search_memory", "search_social_memory", "interaction_event",
                "set_emotion", "get_sensor_data", "set_lights", "oled_face",
                "move_head", "play_sound", "speak", "queue_action",
            ),
            keywords=("autonomy", "idle", "bored", "follow", "behavior", "sinirlen", "mutlu", "duygu", "ifade", "companion"),
        ),
        "calibration": SubAgentProfile(
            module="calibration",
            role="Calibration specialist",
            goal="Plan and verify calibration-safe steps.",
            allowed_tools=("move_head", "get_sensor_data"),
            keywords=("calibration", "zero", "center", "offset", "align"),
        ),
        "camera": SubAgentProfile(
            module="camera",
            role="Camera specialist",
            goal="Interpret visual context from camera outputs.",
            allowed_tools=("get_vision", "get_sensor_data"),
            keywords=("camera", "see", "look", "object", "person", "vision"),
        ),
        "config_center": SubAgentProfile(
            module="config_center",
            role="Config specialist",
            goal="Reason about runtime configuration impact.",
            allowed_tools=("search_memory",),
            keywords=("config", "setting", "yaml", "parameter", "option"),
        ),
        "diagnostics": SubAgentProfile(
            module="diagnostics",
            role="Diagnostics specialist",
            goal="Inspect health and detect anomalies.",
            allowed_tools=("get_sensor_data", "search_memory"),
            keywords=("diagnostic", "health", "error", "fault", "status"),
        ),
        "gateway": SubAgentProfile(
            module="gateway",
            role="Gateway specialist",
            goal="Coordinate service-level API routing context.",
            allowed_tools=("search_memory",),
            keywords=("gateway", "api", "endpoint", "route", "service"),
        ),
        "hardware": SubAgentProfile(
            module="hardware",
            role="Hardware specialist",
            goal="Execute safe physical hardware actions.",
            allowed_tools=("move_head", "get_sensor_data"),
            keywords=("hardware", "head", "servo", "turn", "pan", "tilt"),
        ),
        "interactions": SubAgentProfile(
            module="interactions",
            role="Interaction specialist",
            goal="Trigger high-level interaction events.",
            allowed_tools=("interaction_event", "set_lights", "oled_face", "set_emotion"),
            keywords=("interaction", "react", "event", "scene", "expression", "sinirlen", "mutlu", "duygu", "ifade"),
        ),
        "logwrapper": SubAgentProfile(
            module="logwrapper",
            role="Logging specialist",
            goal="Summarize observability and logging concerns.",
            allowed_tools=("search_memory",),
            keywords=("log", "logging", "trace", "debug"),
        ),
        "neopixel": SubAgentProfile(
            module="neopixel",
            role="Lighting specialist",
            goal="Control body lighting effects safely.",
            allowed_tools=("set_lights", "interaction_event", "set_emotion"),
            keywords=(
                "light", "led", "neopixel", "color", "effect",
                "ışık", "isik", "renk", "kırmızı", "kirmizi", "mavi", "yeşil", "yesil",
            ),
        ),
        "notifier": SubAgentProfile(
            module="notifier",
            role="Notification specialist",
            goal="Produce alerts and notification intent.",
            allowed_tools=("play_sound", "interaction_event"),
            keywords=("notify", "notification", "alert", "warn"),
        ),
        "oled_faces": SubAgentProfile(
            module="oled_faces",
            role="OLED specialist",
            goal="Render eye expressions and face animations.",
            allowed_tools=("oled_face", "interaction_event"),
            keywords=("oled", "face", "eyes", "expression", "blink"),
        ),
        "ollama": SubAgentProfile(
            module="ollama",
            role="LLM specialist",
            goal="Keep response quality and prompt consistency.",
            allowed_tools=("search_memory",),
            keywords=("ollama", "llm", "model", "persona", "prompt"),
        ),
        "piservo": SubAgentProfile(
            module="piservo",
            role="Servo specialist",
            goal="Handle safe pan/tilt operations.",
            allowed_tools=("move_head", "get_sensor_data"),
            keywords=("piservo", "servo", "pan", "tilt"),
        ),
        "scheduler": SubAgentProfile(
            module="scheduler",
            role="Scheduling specialist",
            goal="Plan timed or recurring actions.",
            allowed_tools=("search_memory",),
            keywords=("schedule", "timer", "cron", "later", "remind"),
        ),
        "speak": SubAgentProfile(
            module="speak",
            role="Speech output specialist",
            goal="Shape voice output and response tone.",
            allowed_tools=("speak", "play_sound", "set_emotion"),
            keywords=("speak", "say", "voice", "tts", "reply", "söyle", "soyle", "seslendir", "konuş", "konus"),
        ),
        "speech": SubAgentProfile(
            module="speech",
            role="Speech input specialist",
            goal="Handle listening context and speech flow.",
            allowed_tools=("get_sensor_data",),
            keywords=("speech", "listen", "stt", "microphone", "audio input"),
        ),
        "state_manager": SubAgentProfile(
            module="state_manager",
            role="State specialist",
            goal="Reason about internal robot state changes.",
            allowed_tools=("search_memory", "set_emotion", "get_sensor_data"),
            keywords=("state", "mode", "emotion", "context", "status"),
        ),
        "telemetry": SubAgentProfile(
            module="telemetry",
            role="Telemetry specialist",
            goal="Interpret measurements and reporting context.",
            allowed_tools=("get_sensor_data", "search_memory"),
            keywords=("telemetry", "metric", "report", "monitor"),
        ),
        "vlm_bridge": SubAgentProfile(
            module="vlm_bridge",
            role="Visual cognition specialist",
            goal="Understand current visual world, people identity, scene meaning, person memory, and focus target.",
            allowed_tools=(
                "get_vision", "get_visual_context", "describe_scene",
                "search_memory", "focus_person", "remember_person",
                "update_person_relationship", "ask_vlm_about_scene",
                "get_sensor_data", "start_owner_follow", "stop_follow",
            ),
            keywords=(
                "vlm", "image", "vision", "describe", "recognize",
                "görüyorsun", "çevrede", "kim", "beni", "etrafa",
                "ortam", "sahibi", "yüz", "takip", "geldi", "masada",
                "tehlike", "bak", "kamera", "sahne", "kişi", "tanı",
                "see", "look", "person", "face", "scene", "who",
            ),
        ),
        "wakeword": SubAgentProfile(
            module="wakeword",
            role="Wakeword specialist",
            goal="Handle wake triggers and handoff behavior.",
            allowed_tools=("interaction_event",),
            keywords=("wakeword", "hey", "trigger", "activation"),
        ),
    }

    if not overrides:
        return profiles

    merged = dict(profiles)
    for module_name, raw in overrides.items():
        if module_name not in merged:
            continue
        base = merged[module_name]
        if not isinstance(raw, dict):
            continue
        merged[module_name] = SubAgentProfile(
            module=module_name,
            role=str(raw.get("role", base.role)),
            goal=str(raw.get("goal", base.goal)),
            allowed_tools=tuple(raw.get("allowed_tools", base.allowed_tools)),
            keywords=tuple(raw.get("keywords", base.keywords)),
        )
    return merged


class TriLayerRouter:
    """Low-latency keyword router for module-level sub-agents."""

    def __init__(
        self,
        profiles: Dict[str, SubAgentProfile],
        max_subagents: int = 2,
        default_modules: Sequence[str] | None = None,
    ):
        self.profiles = profiles
        self._absolute_max = 8
        self.max_subagents = self._coerce_max(max_subagents)
        fallback = tuple(default_modules or ("vlm_bridge", "autonomy", "agent_core"))
        self.default_modules = [m for m in fallback if m in profiles]
        if not self.default_modules:
            self.default_modules = ["agent_core"] if "agent_core" in profiles else list(profiles.keys())[:1]

        self._profile_tokens: Dict[str, set[str]] = {}
        for module_name, profile in self.profiles.items():
            toks: set[str] = set()
            for keyword in profile.keywords:
                toks.update(self._tokenize(keyword))
            toks.update(self._tokenize(module_name.replace("_", " ")))
            self._profile_tokens[module_name] = toks

    def _coerce_max(self, value: int) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            n = 1
        return max(1, min(self._absolute_max, n))

    def set_max(self, value: int) -> int:
        """Update the maximum sub-agent count at runtime.

        Returns the value actually applied after clamping to the configured
        absolute bounds.
        """
        self.max_subagents = self._coerce_max(value)
        return self.max_subagents

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        # \w+ is unicode-aware in Python 3, so Turkish and other non-ASCII
        # words (kırmızı, üzgün...) stay intact instead of being split.
        return {t for t in re.findall(r"\w+", str(text or "").lower()) if len(t) > 1}

    def _score_keyword_matches(self, text: str, q_tokens: set[str]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for module_name, profile in self.profiles.items():
            for keyword in profile.keywords:
                key = str(keyword or "").strip().lower()
                if key and key in text:
                    scores[module_name] = scores.get(module_name, 0.0) + 2.5
            p_tokens = self._profile_tokens.get(module_name, set())
            if q_tokens and p_tokens:
                overlap = len(q_tokens & p_tokens)
                if overlap:
                    scores[module_name] = scores.get(module_name, 0.0) + (1.0 + overlap / max(1, len(p_tokens)))
        return scores

    def _apply_semantic_priors(self, q_tokens: set[str], scores: Dict[str, float]) -> None:
        _PRIORS = [
            ({"navigate", "navigation", "route", "where", "location", "path"}, {"agent_core": 1.2, "autonomy": 0.8}),
            ({"health", "fault", "diagnostic", "error", "status"}, {"diagnostics": 1.2}),
            ({"schedule", "timer", "later", "remind", "periodic"}, {"scheduler": 1.1}),
        ]
        for trigger_tokens, boosts in _PRIORS:
            if q_tokens & trigger_tokens:
                for module_name, boost in boosts.items():
                    if module_name in self.profiles:
                        scores[module_name] = scores.get(module_name, 0.0) + boost

    _EMOTION_TOKENS = {
        "sinirlen", "sinirli", "kizgin", "kızgın", "mutlu", "uzgun", "üzgün", "kork",
        "korkmuş", "neşeli", "neseli", "heyecanlı", "heyecanli", "sakin", "yorgun",
        "emotion", "duygu", "duygusu", "duygunu", "durumunu", "ifade", "yuz", "yüz",
        "face", "angry", "happy", "sad", "excited", "bored", "furious", "scared",
        "love", "worried", "confused", "mood", "moral",
    }
    _LIGHT_TOKENS = {
        "led", "ledleri", "ledler", "light", "lights", "neopixel", "neopixelleri",
        "neopixeller", "renk", "rengi", "renkleri", "color", "colour", "ışık", "isik",
        "ışıkları", "isiklari", "kırmızı", "kirmizi", "mavi", "yeşil", "yesil", "sarı",
        "sari", "mor", "turuncu", "pembe", "beyaz", "red", "blue", "green", "yellow",
        "purple", "orange", "pink", "white", "oled", "eyes", "göz", "gözler",
    }
    _EMOTION_PHRASES = (
        "mutlu ol", "sinirli ol", "kizgin ol", "kızgın ol", "uzgun ol", "üzgün ol",
        "kirmizi yan", "kırmızı yan", "yuzunu degistir", "yüzünü değiştir",
        "duygu durumunu", "duygu durumu",
    )

    def _apply_emotion_priors(self, text: str, q_tokens: set[str], scores: Dict[str, float]) -> None:
        emotion_hit = bool(q_tokens & self._EMOTION_TOKENS) or any(p in text for p in self._EMOTION_PHRASES)
        light_hit = bool(q_tokens & self._LIGHT_TOKENS)
        if not (emotion_hit or light_hit):
            return
        if emotion_hit:
            for module_name, boost in {
                "interactions": 2.8, "autonomy": 2.4, "neopixel": 1.8, "oled_faces": 1.6, "speak": 1.0,
            }.items():
                if module_name in self.profiles:
                    scores[module_name] = scores.get(module_name, 0.0) + boost
        if light_hit:
            # Direct lighting commands must win the routing slot even when
            # max_subagents is 1, otherwise set_lights never becomes available.
            for module_name, boost in {"neopixel": 3.5, "interactions": 1.2, "oled_faces": 0.8}.items():
                if module_name in self.profiles:
                    scores[module_name] = scores.get(module_name, 0.0) + boost

    def route(self, user_prompt: str) -> List[str]:
        text = str(user_prompt or "").strip().lower()
        if not text:
            return list(self.default_modules[: self.max_subagents])
        q_tokens = self._tokenize(text)
        scores = self._score_keyword_matches(text, q_tokens)
        self._apply_semantic_priors(q_tokens, scores)
        self._apply_emotion_priors(text, q_tokens, scores)
        if not scores:
            return list(self.default_modules[: self.max_subagents])
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [name for name, _ in ranked[: self.max_subagents]]


# SENTRYBOT compatibility fallback fields for older/newer SubAgentProfile callers.
def _sentrybot_subagent_model(self):
    return (
        _sentrybot_env_os.environ.get("SENTRYBOT_OLLAMA_MODEL")
        or _sentrybot_env_os.environ.get("SENTRYBOT_MODEL")
        or _sentrybot_env_os.environ.get("SENTRYBOT_LLM_MODEL")
        or "qwen3.5:9b"
    )

def _sentrybot_subagent_tools(self):
    return []

if "SubAgentProfile" in globals():
    if not hasattr(SubAgentProfile, "temperature"):
        SubAgentProfile.temperature = property(lambda self: 0.2)
    if not hasattr(SubAgentProfile, "top_p"):
        SubAgentProfile.top_p = property(lambda self: 0.9)
    if not hasattr(SubAgentProfile, "max_tokens"):
        SubAgentProfile.max_tokens = property(lambda self: 512)
    if not hasattr(SubAgentProfile, "max_output_tokens"):
        SubAgentProfile.max_output_tokens = property(lambda self: 512)
    if not hasattr(SubAgentProfile, "timeout"):
        SubAgentProfile.timeout = property(lambda self: 60)
    if not hasattr(SubAgentProfile, "model"):
        SubAgentProfile.model = property(_sentrybot_subagent_model)
    if not hasattr(SubAgentProfile, "tools"):
        SubAgentProfile.tools = property(_sentrybot_subagent_tools)


# SENTRYBOT extra SubAgentProfile Ollama option fallbacks.
def _sentrybot_profile_copy_default(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return value

def _sentrybot_profile_default_property(value):
    return property(lambda self, v=value: _sentrybot_profile_copy_default(v))

if "SubAgentProfile" in globals():
    _sentrybot_profile_defaults = {
        "num_predict": 512,
        "num_ctx": 8192,
        "context_window": 8192,
        "top_k": 20,
        "top_p": 0.9,
        "temperature": 0.2,
        "repeat_penalty": 1.05,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "mirostat": 0,
        "seed": 0,
        "timeout": 60,
        "stream": False,
        "thinking": False,
        "format": None,
        "stop": [],
        "keep_alive": "5m",
        "options": {},
    }
    for _sentrybot_attr, _sentrybot_value in _sentrybot_profile_defaults.items():
        if not hasattr(SubAgentProfile, _sentrybot_attr):
            setattr(SubAgentProfile, _sentrybot_attr, _sentrybot_profile_default_property(_sentrybot_value))

