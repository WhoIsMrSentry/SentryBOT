from __future__ import annotations

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
            allowed_tools=("move_head", "set_laser", "get_sensor_data"),
            keywords=("arduino", "serial", "servo", "motor", "laser"),
        ),
        "autonomy": SubAgentProfile(
            module="autonomy",
            role="Behavior specialist",
            goal="Decide autonomous behavior policy.",
            allowed_tools=("search_memory", "interaction_event", "set_emotion", "get_sensor_data"),
            keywords=("autonomy", "idle", "bored", "follow", "behavior"),
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
            allowed_tools=("move_head", "set_laser", "get_sensor_data"),
            keywords=("hardware", "head", "servo", "turn", "pan", "tilt"),
        ),
        "interactions": SubAgentProfile(
            module="interactions",
            role="Interaction specialist",
            goal="Trigger high-level interaction events.",
            allowed_tools=("interaction_event", "set_lights", "oled_face", "set_emotion"),
            keywords=("interaction", "react", "event", "scene", "expression"),
        ),
        "logwrapper": SubAgentProfile(
            module="logwrapper",
            role="Logging specialist",
            goal="Summarize observability and logging concerns.",
            allowed_tools=("search_memory",),
            keywords=("log", "logging", "trace", "debug"),
        ),
        "mutagen": SubAgentProfile(
            module="mutagen",
            role="Audio metadata specialist",
            goal="Reason about sound metadata and playback context.",
            allowed_tools=("play_sound",),
            keywords=("audio", "music", "metadata", "mutagen", "sound"),
        ),
        "neopixel": SubAgentProfile(
            module="neopixel",
            role="Lighting specialist",
            goal="Control body lighting effects safely.",
            allowed_tools=("set_lights", "interaction_event", "set_emotion"),
            keywords=("light", "led", "neopixel", "color", "effect"),
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
        "ota": SubAgentProfile(
            module="ota",
            role="Update specialist",
            goal="Assess update and rollout safety.",
            allowed_tools=("search_memory",),
            keywords=("ota", "update", "upgrade", "deploy"),
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
            allowed_tools=("play_sound", "set_emotion"),
            keywords=("speak", "say", "voice", "tts", "reply"),
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
        self.max_subagents = max(1, int(max_subagents or 1))
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

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9_]+", str(text or "").lower()) if len(t) > 1}

    def route(self, user_prompt: str) -> List[str]:
        text = str(user_prompt or "").strip().lower()
        if not text:
            return list(self.default_modules[: self.max_subagents])

        q_tokens = self._tokenize(text)

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

        # Small semantic priors for frequent intents.
        if q_tokens & {"navigate", "navigation", "route", "where", "location", "path"}:
            if "agent_core" in self.profiles:
                scores["agent_core"] = scores.get("agent_core", 0.0) + 1.2
            if "autonomy" in self.profiles:
                scores["autonomy"] = scores.get("autonomy", 0.0) + 0.8
        if q_tokens & {"health", "fault", "diagnostic", "error", "status"} and "diagnostics" in self.profiles:
            scores["diagnostics"] = scores.get("diagnostics", 0.0) + 1.2
        if q_tokens & {"schedule", "timer", "later", "remind", "periodic"} and "scheduler" in self.profiles:
            scores["scheduler"] = scores.get("scheduler", 0.0) + 1.1

        if not scores:
            return list(self.default_modules[: self.max_subagents])

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [name for name, _ in ranked[: self.max_subagents]]
