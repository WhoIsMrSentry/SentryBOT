from __future__ import annotations

import re

RUNTIME_CONSOLE_PREVIEW_WARNING_COMPATIBILITY_CONTRACT = True
RUNTIME_CONSOLE_PREVIEW_WARNING_ROLE = "pc_dev_robot_preview_status_classifier"

APP = "SENTRYBOT"
TITLE = "SENTRYBOT CONTROL CENTER"
VERSION = "tui-v16-memory-bias"
DEFAULT_REFRESH = 0.18
MAX_TAIL_BYTES = 2_000_000
MAX_SEARCH_FILE_BYTES = 900_000
SEARCH_EXTS = {".py", ".yml", ".yaml", ".json", ".md", ".txt", ".log", ".ini", ".toml"}
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
TABS = ["Overview", "Logs", "Signals", "Config", "Search", "Companion", "Expression", "Camera", "Help"]

PC_EXPECTED_HINTS = (
    "ESP bridge unreachable",
    "ESP bridge unreachable - expected on PC tests",
    "animate degraded",
    "pose step skipped",
    "Speech/STT unavailable",
    "speech stt unavailable",
    "speech start rejected",
    "stt_unavailable",
    "openwakeword unavailable",
    "piper unavailable",
    "Piper voice model is missing",
    "Piper model missing",
    "piper.model_path not found",
    "TR-dfki",
    "OpenCV not available",
    "OpenCV face cascade disabled",
    "face cascade disabled",
    "No speak_fn set",
    "no speaker function",
    "Speech arbiter has no speaker function",
    "LLM chat unavailable",
    "LLM provider unavailable",
    "Ollama unavailable",
    "Ollama daemon unavailable",
    "remote Ollama unavailable",
    "remote AI unavailable",
    "model unavailable",
    "model_available:false",
    "model_available=false",
    "daemon_ok:false",
    "daemon_ok=false",
    "api/tags",
    "Max retries exceeded",
    "ConnectTimeoutError",
    "Connection refused",
    "Connection to 127.0.0.1 timed out",
    "Connection to 192.",
    "qwen3.5:9b",
)

SERVICE_RULES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "CORE": (
        ("Application startup complete", "OK", "runtime ready"),
        ("Loaded gateway config", "OK", "gateway config loaded"),
        ("Shutdown", "IDLE", "stopping"),
    ),
    "AI": (
        ("LLM provider client ready", "OK", "provider ready"),
        ("Vision LLM client initialized", "OK", "vision provider ready"),
        ("api_key is missing", "ERR", "Google API key missing"),
        ("LLM chat failed", "ERR", "LLM endpoint failed"),
        ("Provider client init failed", "ERR", "provider init failed"),
        ("fallback to ollama", "WARN", "fallback provider"),
    ),
    "VISION": (
        ("Vision LLM client initialized", "OK", "vision provider ready"),
        ("Remote mode: waiting", "IDLE", "remote result mode"),
        ("OpenCV not available", "WARN", "OpenCV/cascade disabled"),
        ("VLM client init failed", "ERR", "VLM init failed"),
        ("Loaded 3 person records", "OK", "person DB loaded"),
    ),
    "AUDIO": (
        ("wakeword listening started", "OK", "wakeword listening"),
        ("SpeechArbiter started", "OK", "speech arbiter"),
        ("Speech/STT unavailable", "ERR", "STT backend unavailable"),
        ("speech stt unavailable", "ERR", "STT unavailable"),
        ("speech start rejected", "WARN", "STT unavailable"),
        ("openwakeword unavailable", "WARN", "openwakeword unavailable"),
    ),
    "TTS": (
        ("First audio", "OK", "audio started"),
        ("piper unavailable", "WARN", "Piper model missing"),
        ("dummy", "WARN", "test-tone voice compatibility warning"),
    ),
    "MOVE": (
        ("ESP bridge unreachable", "WARN", "ESP bridge unreachable"),
        ("animate degraded", "WARN", "animation degraded"),
        ("pose step skipped", "WARN", "pose skipped"),
    ),
    "CONFIG": (
        ("changeme", "WARN", "default token"),
        ("no api_keys configured", "WARN", "gateway API keys missing"),
    ),
}

CHANNEL_HINTS = {
    "AI": ("agent", "ollama", "google", "gemini", "llm", "provider"),
    "VISION": ("vlm", "vision", "camera", "opencv", "face", "qwen", "imx"),
    "AUDIO": ("wakeword", "speech", "stt", "microphone", "audio"),
    "TTS": ("speak", "tts", "piper", "voice", "glados"),
    "MOVE": ("arduino", "esp", "servo", "animate", "motor", "piservo"),
    "FACE": ("oled", "neopixel", "expression", "emotion"),
    "MEMORY": ("memory", "rag", "social", "slam", "map"),
}

NOISE_HINTS = (
    "Starting new HTTP connection",
    "GET /state/get",
    "GET /speech/last",
    "GET /speech/direction",
    "GET /vlm/context/latest",
    "GET /vlm/results/latest",
    "POST /arduino/request",
    "POST /interactions/event",
    "POST /interactions/effect",
    "POST /neopixel/animate",
    "POST /oled_faces/manual",
)

BLOCKER_HINTS = (
    ("piper unavailable", "TTS", "Piper voice model is missing"),
    ("Speech/STT unavailable", "AUDIO", "Speech recognition unavailable"),
    ("ESP bridge unreachable", "MOVE", "ESP bridge unreachable - expected on PC tests"),
    ("OpenCV not available", "VISION", "OpenCV face cascade disabled"),
    ("api_key is missing", "AI", "Google API key missing"),
    ("changeme", "CONFIG", "Default security token still configured"),
)

SYSTEM_WARNING_HINTS = (
    "CPU warm",
    "CPU load high",
    "Memory pressure",
    "Disk space low",
    "Network latency spike",
    "Degraded mode active",
    "Fallback provider active",
)

SYSTEM_ERROR_HINTS = (
    "Hardware failure",
    "Critical process died",
    "Camera pipeline failed",
    "Audio stream overflow",
    "Motor stall detected",
)
