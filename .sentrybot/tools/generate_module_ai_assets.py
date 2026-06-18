#!/usr/bin/env python3
"""Generate module-specific AI assets with semantic code analysis.

Obsidian notes include: named classes, methods, API handlers, internal wiring,
cross-module imports, HTTP integrations, and full source archive.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = ROOT / "modules"
REGISTRY_PATH = ROOT / ".sentrybot" / "context" / "module-registry.md"

SKILLS_DIR = ROOT / ".sentrybot" / "skills" / "modules"
SUB_AGENTS_DIR = ROOT / ".sentrybot" / "agents" / "sub"
OBSIDIAN_MODULES_DIR = ROOT / ".sentrybot" / "obsidian" / "modules"

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "_irisoled_src", ".git", ".pytest_cache"}
INCLUDE_SUFFIXES = {
    ".py", ".md", ".yml", ".yaml", ".txt", ".json",
    ".html", ".js", ".css", ".ini", ".env.example",
}

LANG_MAP = {
    ".py": "python", ".md": "markdown", ".yml": "yaml", ".yaml": "yaml",
    ".json": "json", ".html": "html", ".js": "javascript", ".css": "css",
    ".txt": "text", ".ini": "ini", ".env.example": "bash",
}


@dataclass
class ModuleInfo:
    name: str
    port: str
    layer: str
    mission: str
    uses_arduino: str
    dependencies: str


@dataclass
class ClassInfo:
    name: str
    file: str
    doc: str
    bases: list[str]
    methods: list[str]
    composes: list[str]  # self.x = SomeClass() in __init__


@dataclass
class EndpointInfo:
    method: str
    path: str
    handler: str
    doc: str
    calls: list[str]


@dataclass
class ExternalLink:
    target_module: str
    link_type: str  # import | http | arduino | registry
    detail: str


@dataclass
class InboundLink:
    source_module: str
    link_type: str
    detail: str


@dataclass
class SourceFile:
    rel_path: str
    content: str
    line_count: int


@dataclass
class ModuleAnalysis:
    main_class: str | None
    main_file: str | None
    entry_point: str | None = None
    orchestrator: str | None = None
    classes: list[ClassInfo] = field(default_factory=list)
    endpoints: list[EndpointInfo] = field(default_factory=list)
    outbound: list[ExternalLink] = field(default_factory=list)
    inbound: list[InboundLink] = field(default_factory=list)
    config_sections: list[str] = field(default_factory=list)
    mermaid_blocks: list[str] = field(default_factory=list)
    source_files: list[SourceFile] = field(default_factory=list)

    @property
    def total_lines(self) -> int:
        return sum(f.line_count for f in self.source_files)

    @property
    def file_count(self) -> int:
        return len(self.source_files)


# ─── parsers ─────────────────────────────────────────────────────────────────

def _sanitize_cell(value: str) -> str:
    return value.strip().strip("`")


def parse_registry_modules(registry_text: str) -> list[ModuleInfo]:
    modules: list[ModuleInfo] = []
    for line in registry_text.splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) != 7 or not re.fullmatch(r"\d+", parts[0]):
            continue
        modules.append(ModuleInfo(
            name=_sanitize_cell(parts[1]), port=_sanitize_cell(parts[2]),
            layer=_sanitize_cell(parts[3]), mission=_sanitize_cell(parts[4]),
            uses_arduino=_sanitize_cell(parts[5]), dependencies=_sanitize_cell(parts[6]),
        ))
    return modules


def _first_line(doc: str | None) -> str:
    if not doc:
        return ""
    return doc.strip().split("\n")[0][:200]


def _extract_classes_from_ast(path: Path, rel: str) -> list[ClassInfo]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []

    classes: list[ClassInfo] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = [
            n.name for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        ]
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(b.attr)

        composes: list[str] = []
        init = next((n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
        if init:
            for stmt in ast.walk(init):
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    target = stmt.targets[0]
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                        val = stmt.value
                        if isinstance(val, ast.Call):
                            fn = val.func
                            name = None
                            if isinstance(fn, ast.Name):
                                name = fn.id
                            elif isinstance(fn, ast.Attribute):
                                name = fn.attr
                            if name and name[0].isupper():
                                composes.append(name)

        classes.append(ClassInfo(
            name=node.name, file=rel, doc=_first_line(ast.get_docstring(node)),
            bases=bases, methods=methods[:12], composes=composes,
        ))
    return classes


def _extract_endpoints(router_path: Path) -> list[EndpointInfo]:
    if not router_path.exists():
        return []
    text = router_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    endpoints: list[EndpointInfo] = []

    route_re = re.compile(
        r'@(?:\w+\.)?(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    i = 0
    while i < len(lines):
        m = route_re.search(lines[i])
        if not m:
            i += 1
            continue
        method, path = m.group(1).upper(), m.group(2)
        handler, doc, calls = "", "", []
        for j in range(i + 1, min(i + 30, len(lines))):
            fn_m = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", lines[j])
            if fn_m:
                handler = fn_m.group(1)
                body = "\n".join(lines[j:min(j + 40, len(lines))])
                doc_m = re.search(r'"""(.*?)"""', body, re.DOTALL)
                if doc_m:
                    doc = _first_line(doc_m.group(1))
                for call_m in re.finditer(r"(?:service|svc|anim|self)\.(\w+)\s*\(", body):
                    calls.append(call_m.group(1))
                for call_m in re.finditer(r"await\s+asyncio\.to_thread\(\s*\w+\.(\w+)", body):
                    calls.append(call_m.group(1))
                break
        endpoints.append(EndpointInfo(method=method, path=path, handler=handler, doc=doc, calls=sorted(set(calls))))
        i += 1
    return endpoints


def _extract_imports(text: str, known_modules: set[str], this_module: str) -> list[ExternalLink]:
    links: list[ExternalLink] = []
    seen: set[tuple[str, str]] = set()

    for m in re.finditer(r"from\s+modules\.([a-zA-Z_][\w]*)\s+import\s+([^\n#]+)", text):
        mod, syms_raw = m.group(1), m.group(2)
        if mod not in known_modules or mod == this_module:
            continue
        syms = [s.strip().split(" as ")[0].strip() for s in syms_raw.split(",")]
        syms = [s for s in syms if s and s != "("][:8]
        key = (mod, ",".join(syms))
        if key not in seen:
            seen.add(key)
            links.append(ExternalLink(mod, "import", ", ".join(syms)))

    for m in re.finditer(r"\bmodules\.([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)", text):
        mod, sym = m.group(1), m.group(2)
        if mod in known_modules and mod != this_module:
            key = (mod, sym)
            if key not in seen:
                seen.add(key)
                links.append(ExternalLink(mod, "import", sym))

    return links


def _extract_http_links(text: str, known_modules: set[str], this_module: str) -> list[ExternalLink]:
    links: list[ExternalLink] = []
    path_to_module = {
        "speak": "speak", "speech": "speech", "ollama": "ollama",
        "arduino": "arduino_serial", "interactions": "interactions",
        "vlm": "vlm_bridge", "vision": "vlm_bridge", "agent": "agent_core",
        "camera": "camera", "neopixel": "neopixel", "animate": "animate",
        "social": "social_db", "config": "config_center", "gateway": "gateway",
        "wakeword": "wakeword", "diagnostics": "diagnostics",
    }
    for m in re.finditer(r'["\'](/[a-zA-Z_][\w/{}]*?)["\']', text):
        p = m.group(1).split("{")[0].rstrip("/")
        seg = p.strip("/").split("/")[0] if p.strip("/") else ""
        target = path_to_module.get(seg)
        if target and target != this_module and target in known_modules:
            links.append(ExternalLink(target, "http", f"calls path `{p}`"))

    for m in re.finditer(r"gateway_url\(\s*['\"]([^'\"]+)['\"]", text):
        p = m.group(1)
        seg = p.strip("/").split("/")[0]
        target = path_to_module.get(seg)
        if target and target != this_module:
            links.append(ExternalLink(target, "http", f"gateway_url('{p}')"))

    if (
        "arduino_serial" in known_modules
        and this_module != "arduino_serial"
        and re.search(r"from\s+modules\.arduino_serial|xArduinoSerialService|contract\.build_", text)
    ):
        links.append(ExternalLink("arduino_serial", "arduino", "Arduino serial / contract kullanımı"))

    return links


def _extract_mermaid(arch_path: Path) -> list[str]:
    if not arch_path.exists():
        return []
    text = arch_path.read_text(encoding="utf-8", errors="ignore")
    return re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL)


def _config_sections(config_path: Path) -> list[str]:
    if not config_path.exists():
        return []
    sections: list[str] = []
    for line in config_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^([A-Za-z0-9_]+)\s*:", line)
        if m and not line.startswith(" "):
            sections.append(m.group(1))
    return sections


def _detect_entry_and_orchestrator(module_name: str) -> tuple[str | None, str | None, str | None]:
    """Return (file, entry_point, orchestrator_class) for create_app-style modules."""
    pascal = "".join(c.capitalize() for c in module_name.split("_"))
    skip = {"FastAPI", "Path", "APIRouter", "CaptureConfig", "NeoDriverConfig", "Servo", "OutputConfig", "TTSConfig"}
    prefer = ("Runner", "Processor", "Service", "Capture", "Brain", "Store", "Orchestrator", "Publisher")

    for fname in (f"x{pascal}Service.py", f"x{module_name}Service.py"):
        path = MODULES_DIR / module_name / fname
        if not path.exists():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "def create_app" not in text:
            continue

        candidates: list[str] = []
        for m in re.finditer(r"(\w+)\s*=\s*([A-Z][A-Za-z0-9_]*)\s*\(", text):
            cls = m.group(2)
            if cls in skip or cls.endswith("Config"):
                continue
            candidates.append(cls)

        orchestrator = None
        for suffix in prefer:
            orchestrator = next((c for c in candidates if c.endswith(suffix)), None)
            if orchestrator:
                break
        if not orchestrator and candidates:
            orchestrator = candidates[-1]
        return rel, "create_app()", orchestrator
    return None, None, None


def _find_main_class(module_name: str, classes: list[ClassInfo]) -> tuple[str | None, str | None]:
    pascal = "".join(c.capitalize() for c in module_name.split("_"))
    root_patterns = [
        f"modules/{module_name}/x{pascal}Service.py",
        f"modules/{module_name}/x{module_name}Service.py",
    ]
    for pattern in root_patterns:
        for cls in classes:
            if cls.file == pattern:
                return cls.name, cls.file

    for cls in classes:
        if (
            cls.file.startswith(f"modules/{module_name}/x")
            and cls.file.endswith("Service.py")
            and cls.file.count("/") == 3
            and "/tests/" not in cls.file
        ):
            return cls.name, cls.file

    for cls in classes:
        if cls.name.endswith("Service") and "/tests/" not in cls.file and "/services/" not in cls.file:
            return cls.name, cls.file

    prod = [c for c in classes if "/tests/" not in c.file and "/services/" not in c.file]
    return (prod[0].name, prod[0].file) if prod else (None, None)


def collect_source_files(module_name: str) -> list[SourceFile]:
    base = MODULES_DIR / module_name
    if not base.exists():
        return []
    files: list[SourceFile] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any(p in EXCLUDE_DIR_NAMES for p in path.parts):
            continue
        if path.suffix.lower() not in INCLUDE_SUFFIXES and path.name not in {"requirements.txt"}:
            continue
        if path.stat().st_size > 500_000:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        files.append(SourceFile(
            rel_path=str(path.relative_to(ROOT)).replace("\\", "/"),
            content=content, line_count=len(content.splitlines()),
        ))
    return files


def analyze_module(module_name: str, info: ModuleInfo, known_modules: set[str]) -> ModuleAnalysis:
    base = MODULES_DIR / module_name
    analysis = ModuleAnalysis(main_class=None, main_file=None)
    analysis.source_files = collect_source_files(module_name)
    analysis.config_sections = _config_sections(base / "config" / "config.yml")
    analysis.mermaid_blocks = _extract_mermaid(base / f"architecture_{module_name}.md")
    analysis.endpoints = _extract_endpoints(base / "api" / "router.py")

    all_classes: list[ClassInfo] = []
    all_text = ""
    outbound_map: dict[tuple[str, str, str], ExternalLink] = {}

    for sf in analysis.source_files:
        if not sf.rel_path.endswith(".py"):
            continue
        path = ROOT / sf.rel_path
        all_classes.extend(_extract_classes_from_ast(path, sf.rel_path))
        text = sf.content
        all_text += text + "\n"
        for link in _extract_imports(text, known_modules, module_name):
            outbound_map[(link.target_module, link.link_type, link.detail)] = link
        for link in _extract_http_links(text, known_modules, module_name):
            outbound_map[(link.target_module, link.link_type, link.detail)] = link

    declared = info.dependencies.strip().lower()
    if "arduino" in info.uses_arduino.lower() and module_name != "arduino_serial":
        outbound_map[("arduino_serial", "registry", "hardware commands")] = ExternalLink(
            "arduino_serial", "registry", "declared Arduino user in module-registry"
        )
    for dep in re.findall(r"[a-z_]+", declared):
        if dep in known_modules and dep != module_name:
            outbound_map[(dep, "registry", info.dependencies)] = ExternalLink(
                dep, "registry", f"registry dependency: {info.dependencies}"
            )

    analysis.classes = sorted(all_classes, key=lambda c: (c.file, c.name))
    analysis.main_class, analysis.main_file = _find_main_class(module_name, analysis.classes)
    entry_file, entry_fn, orchestrator = _detect_entry_and_orchestrator(module_name)
    if entry_fn:
        analysis.entry_point = entry_fn
        analysis.orchestrator = orchestrator
        if entry_file:
            analysis.main_file = entry_file
        if orchestrator and (
            not analysis.main_class or analysis.main_class.endswith(("Request", "Response", "Result"))
        ):
            analysis.main_class = orchestrator
    analysis.outbound = sorted(outbound_map.values(), key=lambda l: (l.target_module, l.link_type))
    return analysis


def scan_inbound_links(
    module_name: str,
    all_analyses: dict[str, ModuleAnalysis],
    known_modules: set[str],
) -> list[InboundLink]:
    inbound: list[InboundLink] = []
    seen: set[tuple[str, str, str]] = set()

    for other, analysis in all_analyses.items():
        if other == module_name:
            continue
        for link in analysis.outbound:
            if link.target_module != module_name:
                continue
            key = (other, link.link_type, link.detail)
            if key not in seen:
                seen.add(key)
                inbound.append(InboundLink(other, link.link_type, link.detail))

        for ep in analysis.endpoints:
            if f"/{module_name}/" in ep.path or ep.path.startswith(f"/{module_name}"):
                key = (other, "http", f"{ep.method} {ep.path}")
                if key not in seen:
                    seen.add(key)
                    inbound.append(InboundLink(other, "http", f"exposes/routes to `{ep.path}`"))

    if module_name == "gateway":
        for other in sorted(known_modules):
            if other != "gateway":
                inbound.append(InboundLink(other, "mount", f"`{other}` router gateway'e mount edilir"))

    return sorted(inbound, key=lambda l: (l.source_module, l.link_type))


# ─── relationship "why" explanations ───────────────────────────────────────

_PAIR_WHY: dict[tuple[str, str], str] = {
    ("autonomy", "speak"): "Sense-Think-Act döngüsü LLM yanıtını seslendirmek için TTS çağırır.",
    ("autonomy", "ollama"): "Duygu motoru ve karar üretimi için yerel LLM'e sorar.",
    ("autonomy", "vlm_bridge"): "Görsel bağlam ve yüz tanıma verisi alır.",
    ("autonomy", "arduino_serial"): "Karar sonrası servo/hareket komutlarını donanıma iletir.",
    ("autonomy", "agent_core"): "Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.",
    ("autonomy", "social_db"): "Kişi hafızası ve ilişki seviyelerini okur/günceller.",
    ("agent_core", "ollama"): "Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.",
    ("agent_core", "autonomy"): "Alt sistem olarak otonomi beyin döngüsünü tetikler.",
    ("agent_core", "vlm_bridge"): "Görsel araçlar ve vision context için VLM köprüsüne bağlanır.",
    ("agent_core", "social_db"): "Kullanıcı/tanıma verisi için sosyal hafızayı kullanır.",
    ("speech", "speak"): "ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.",
    ("speech", "arduino_serial"): "Ses yönü (DOA) veya buzzer geri bildirimi için Arduino'ya komut gönderir.",
    ("wakeword", "speech"): "Wake kelime algılandığında ASR pipeline'ını başlatır.",
    ("wakeword", "arduino_serial"): "Algılama anında buzzer/LED geri bildirimi tetikler.",
    ("vlm_bridge", "camera"): "MJPEG/frame kaynağı olarak kamera stream'ini kullanır.",
    ("vlm_bridge", "arduino_serial"): "Pan/tilt servo takibi için Arduino komutları gönderir.",
    ("vlm_bridge", "ollama"): "Remote VLM veya scene caption için LLM'e danışır.",
    ("vlm_bridge", "social_db"): "Yüz tanıma sonuçlarını kişi kaydına yazar.",
    ("speak", "neopixel"): "Konuşma sırasında LED canlılık efektleri (liveliness) tetikler.",
    ("speak", "interactions"): "Konuşma başı/sonu event ve efekt API'sine HTTP ile bildirir.",
    ("speak", "common"): "Duygu tonu ve emotion_vocab ile TTS tonunu eşler.",
    ("speak", "config_center"): "config/agent.yaml içindeki speak ayarlarını okur.",
    ("interactions", "neopixel"): "Kural motoru CPU/ağ olaylarında LED animasyonu tetikler.",
    ("interactions", "hardware"): "Sistem metriklerini (CPU, RAM, sıcaklık) okur.",
    ("animate", "arduino_serial"): "YAML animasyon adımlarını set_pose komutlarına çevirir.",
    ("autonomy", "animate"): "Duygu durumuna göre vücut animasyonu (stretch, sit, look_around) tetikler.",
    ("interactions", "animate"): "Sistem olaylarında veya kural tetiklerinde robot hareketi başlatır.",
    ("neopixel", "animate"): "LED efektleri ile senkronize fiziksel hareket üretir.",
    ("calibration", "arduino_serial"): "Servo kalibrasyon komutlarını Arduino'ya gönderir.",
    ("piservo", "arduino_serial"): "Kulak servo komutları için seri haberleşme (bazı kurulumlarda).",
    ("diagnostics", "arduino_serial"): "Arduino bağlantı sağlık testi yapar.",
    ("diagnostics", "camera"): "Kamera erişim ve stream testi yapar.",
    ("diagnostics", "ollama"): "Ollama servis erişilebilirlik testi yapar.",
    ("gateway", "arduino_serial"): "Tüm /arduino/* isteklerini serial modüle proxy eder.",
    ("scheduler", "speak"): "Zamanlanmış görevlerde hatırlatma/duyuru metni seslendirir.",
    ("admin_ui", "gateway"): "Tek port üzerinden tüm modül API'lerine erişir.",
    ("config_center", "gateway"): "Runtime config ve modül registry gateway ile senkronize edilir.",
    ("mutagen", "logwrapper"): "Senkronizasyon loglarını merkezi log sistemine yazar.",
    ("ollama", "config_center"): "LLM model ve persona ayarlarını merkezi config'den okur.",
    ("hardware", "autonomy"): "Sistem yükü verisini otonomi beyinine bildirir.",
    ("oled_faces", "common"): "Yüz ifadesi ve duygu taksonomisini ortak sözlükten alır.",
    ("neopixel", "common"): "23 duygu paleti emotion_vocab ile hizalanır.",
    ("piservo", "common"): "Kulak pozisyonları duygu sözlüğü ile eşlenir.",
}

_SYMBOL_WHY: dict[str, str] = {
    "emotion_vocab": "Kanonik duygu taksonomisi (tone/LED/yüz) için ortak sözlük.",
    "emotion_render": "Duygu etiketini somut çıktı parametrelerine çevirir.",
    "contract": "Arduino komut payload'ını kontrat builder ile üretir.",
    "xArduinoSerialService": "Doğrudan seri port üzerinden Arduino iletişimi.",
    "init_logging": "Merkezi WebSocket log yayınına bağlanır.",
    "agent_yaml_loader": "config/agent.yaml dosyasından ayar okur.",
    "gateway_url": "Gateway tek port üzerinden modül API'sine erişir.",
    "load_config": "Modül YAML config'ini yükler.",
    "SocialDB": "SQLite kişi ve ilişki hafızası.",
    "AgentOrchestrator": "3 katmanlı ajan orkestrasyonu (Router→Sub-Agent→Persona).",
    "VisionProcessor": "OpenCV yüz algılama ve VLM işleme.",
    "TextToSpeech": "TTS motor seçimi ve sentez pipeline'ı.",
    "NeoRunner": "NeoPixel animasyon ve duygu preset yürütücüsü.",
    "AutonomyBrain": "Sense-Think-Act ana beyin döngüsü.",
}

_PATH_WHY: list[tuple[str, str]] = [
    ("/speak/say", "Metin sentezleyip hoparlörden çalar (TTS)."),
    ("/speak/status", "TTS servisinin hazır olup olmadığını kontrol eder."),
    ("/speak/stop", "Devam eden konuşmayı keser."),
    ("/speak/play", "Hazır WAV verisini doğrudan çalar."),
    ("/speech/", "Ses tanıma (ASR) pipeline'ına istek gönderir."),
    ("/animate/", "YAML tabanlı servo animasyonu başlatır."),
    ("/arduino/", "Arduino'ya NDJSON komut gönderir veya ACK bekler."),
    ("/interactions/", "Sistem olayı veya LED efekti tetikler."),
    ("/ollama/", "Yerel LLM sohbet/completion isteği yapar."),
    ("/vision", "Görüntü analizi veya yüz tanıma ister."),
    ("/agent", "Ajan orkestrasyonu ve tool-calling çağrısı."),
    ("/camera", "Kamera stream veya snapshot ister."),
    ("/neopixel/", "LED animasyon veya duygu preset uygular."),
    ("/config", "Merkezi yapılandırma okur/yazar."),
    ("/diagnostics", "Sistem sağlık kontrolü çalıştırır."),
    ("/social", "Kişi hafızası ve ilişki verisi okur/yazar."),
]


def _mission_short(module_map: dict[str, ModuleInfo], name: str) -> str:
    info = module_map.get(name)
    return info.mission if info else name


def explain_outbound(
    source: str,
    link: ExternalLink,
    module_map: dict[str, ModuleInfo],
) -> str:
    pair = (source, link.target_module)
    if pair in _PAIR_WHY:
        return _PAIR_WHY[pair]

    if link.link_type == "registry":
        return (
            f"Registry kaydı: `{source}` modülü `{link.target_module}` ile mimari olarak eşleştirilmiş "
            f"({_mission_short(module_map, link.target_module)})."
        )

    if link.link_type == "arduino":
        return (
            f"`{source}` fiziksel hareket/servo/buzzer çıktısı için Arduino seri katmanına "
            f"(`{_mission_short(module_map, 'arduino_serial')}`) güvenir."
        )

    if link.link_type == "import":
        for sym, why in _SYMBOL_WHY.items():
            if sym in link.detail:
                return f"`{source}` → `{link.target_module}`: {why}"
        target_mission = _mission_short(module_map, link.target_module)
        return (
            f"`{source}` içinde `{link.detail}` import edilir; "
            f"`{link.target_module}` modülünün yeteneğini kullanır ({target_mission})."
        )

    if link.link_type == "http":
        detail_norm = link.detail.replace("`", "")
        for prefix, why in _PATH_WHY:
            p = prefix.rstrip("/")
            if p in detail_norm or f"path {p}" in detail_norm:
                return f"`{source}` HTTP ile `{link.target_module}` modülüne erişir: {why}"
        return (
            f"`{source}` gateway veya doğrudan HTTP ile `{link.target_module}` API'sini çağırır "
            f"({link.detail})."
        )

    return f"`{source}` modülü `{link.target_module}` ile entegre çalışır."


def explain_inbound(
    target: str,
    link: InboundLink,
    module_map: dict[str, ModuleInfo],
) -> str:
    pair = (link.source_module, target)
    if pair in _PAIR_WHY:
        return _PAIR_WHY[pair]

    if link.link_type == "mount":
        return (
            f"`{link.source_module}` modülünün FastAPI router'ı gateway (8080) üzerinden "
            f"tek portta dış dünyaya açılır."
        )

    if link.link_type == "registry":
        return (
            f"`{link.source_module}` registry'de `{target}` modülüne bağımlı olarak tanımlı; "
            f"runtime'da bu modülün API/servisine ihtiyaç duyar."
        )

    if link.link_type == "arduino":
        return f"`{link.source_module}` donanım çıktısı için `{target}` üzerinden Arduino komutu gönderir."

    if link.link_type == "import":
        for sym, why in _SYMBOL_WHY.items():
            if sym in link.detail:
                return f"`{link.source_module}` `{target}` modülünden `{sym}` kullanır: {why}"
        return (
            f"`{link.source_module}` kod içinde `{target}` modülünü import eder "
            f"(`{link.detail}`) — {_mission_short(module_map, target)}."
        )

    if link.link_type == "http":
        detail_norm = link.detail.replace("`", "")
        for prefix, why in _PATH_WHY:
            p = prefix.rstrip("/")
            if p in detail_norm or f"path {p}" in detail_norm or f"routes to `{p}" in detail_norm:
                return f"`{link.source_module}` → `{target}`: {why}"
        return f"`{link.source_module}` `{target}` modülünün HTTP API'sine istek atar ({link.detail})."

    return f"`{link.source_module}` modülü `{target}` ile çalışmak için bağlanır."


# ─── note builders ───────────────────────────────────────────────────────────

def bulletize(items: list[str], fallback: str = "—") -> str:
    return "\n".join(f"- {i}" for i in items) if items else f"- {fallback}"


def table_rows(rows: list[list[str]]) -> str:
    if not rows:
        return "| — | — |\n| --- | --- |"
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
    return f"{header}\n{sep}\n{body}"


def build_internal_mermaid(analysis: ModuleAnalysis, module_name: str) -> str:
    lines = ["flowchart TB"]
    main = analysis.main_class or module_name
    lines.append(f"    API[FastAPI Router] --> {main}[{main}]")

    service_classes = [c for c in analysis.classes if "/services/" in c.file and not c.name.startswith("_")]
    for cls in service_classes[:10]:
        safe = re.sub(r"[^a-zA-Z0-9_]", "", cls.name)
        lines.append(f"    {main} --> {safe}[{cls.name}]")

    main_cls = next((c for c in analysis.classes if c.name == analysis.main_class), None)
    if main_cls:
        for comp in main_cls.composes[:8]:
            safe = re.sub(r"[^a-zA-Z0-9_]", "", comp)
            lines.append(f"    {main} -->|composes| {safe}[{comp}]")

    return "\n".join(lines)


def build_external_mermaid(module_name: str, outbound: list[ExternalLink], inbound: list[InboundLink]) -> str:
    lines = ["flowchart LR", f"    M[{module_name}]"]
    for link in outbound[:12]:
        safe = re.sub(r"[^a-zA-Z0-9_]", "", link.target_module)
        lines.append(f"    M -->|{link.link_type}| {safe}[{link.target_module}]")
    for link in inbound[:12]:
        safe = re.sub(r"[^a-zA-Z0-9_]", "", link.source_module)
        lines.append(f"    {safe}[{link.source_module}] -->|{link.link_type}| M")
    return "\n".join(lines)


def format_class_section(cls: ClassInfo) -> str:
    methods = ", ".join(f"`{m}()`" for m in cls.methods) if cls.methods else "—"
    composes = ", ".join(f"`{c}`" for c in cls.composes) if cls.composes else "—"
    bases = ", ".join(cls.bases) if cls.bases else "—"
    return f"""#### `{cls.name}` — `{cls.file}`
- **Görev:** {cls.doc or "—"}
- **Kalıtım:** {bases}
- **Oluşturduğu bileşenler:** {composes}
- **Metodlar:** {methods}
"""


def fence_lang(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if path.endswith("requirements.txt"):
        return "text"
    return LANG_MAP.get(suffix, "text")


def obsidian_module_note(module: ModuleInfo, analysis: ModuleAnalysis, module_map: dict[str, ModuleInfo]) -> str:
    layer_tag = module.layer.lower().replace(" ", "-").replace("/", "-")

    class_sections = "\n".join(format_class_section(c) for c in analysis.classes if "/tests/" not in c.file)
    if not class_sections:
        class_sections = "—\n"

    ep_rows = [["HTTP", "Path", "Handler", "Çağırdığı servis", "Açıklama"]]
    for ep in analysis.endpoints:
        ep_rows.append([
            ep.method, f"`{ep.path}`", f"`{ep.handler}()`",
            ", ".join(f"`{c}()`" for c in ep.calls) or "—",
            ep.doc or "—",
        ])

    out_rows = [["Hedef modül", "Bağlantı tipi", "Detay", "Neden"]]
    for link in analysis.outbound:
        out_rows.append([
            f"[[{link.target_module}]]", link.link_type, link.detail,
            explain_outbound(module.name, link, module_map),
        ])

    in_rows = [["Kaynak modül", "Bağlantı tipi", "Detay", "Neden"]]
    for link in analysis.inbound:
        in_rows.append([
            f"[[{link.source_module}]]", link.link_type, link.detail,
            explain_inbound(module.name, link, module_map),
        ])

    mermaid_docs = ""
    for i, block in enumerate(analysis.mermaid_blocks[:3]):
        mermaid_docs += f"\n### Mimari diyagram {i + 1}\n```mermaid\n{block.strip()}\n```\n"

    source_blocks = "\n".join(
        f"### `{sf.rel_path}` ({sf.line_count} satır)\n\n```{fence_lang(sf.rel_path)}\n{sf.content.rstrip()}\n```\n"
        for sf in analysis.source_files
    )

    same_layer_peers = []  # filled by caller via frontmatter if needed

    return f"""---
tags: [sentrybot, module, {layer_tag}, knowledge-base]
module: {module.name}
main_class: {analysis.main_class or "unknown"}
layer: {module.layer}
port: {module.port}
arduino: {module.uses_arduino}
class_count: {len(analysis.classes)}
endpoint_count: {len(analysis.endpoints)}
file_count: {analysis.file_count}
total_lines: {analysis.total_lines}
---

# {module.name}

> **{module.mission}**

## Kimlik
| Alan | Değer |
| --- | --- |
| Ana sınıf | `{analysis.main_class or "—"}` |
| Giriş noktası | `{analysis.entry_point or "—"}` |
| Orkestratör | `{analysis.orchestrator or "—"}` |
| Ana dosya | `{analysis.main_file or "—"}` |
| Katman | {module.layer} |
| Port | {module.port} |
| Arduino | {module.uses_arduino} |
| Sınıf sayısı | {len(analysis.classes)} |
| Endpoint sayısı | {len(analysis.endpoints)} |

## İsimlendirilmiş Bileşenler (Sınıflar)

{class_sections}

## API — Endpoint → Handler → Servis

{table_rows(ep_rows)}

## Config Bölümleri
{bulletize([f"`{s}`" for s in analysis.config_sections])}

## Dış İlişkiler (Bu modül → diğerleri)

{table_rows(out_rows)}

## Gelen İlişkiler (Diğerleri → bu modül)

{table_rows(in_rows)}

## İç Mimari (otomatik çıkarım)

```mermaid
{build_internal_mermaid(analysis, module.name)}
```

## Modül Etkileşim Haritası

```mermaid
{build_external_mermaid(module.name, analysis.outbound, analysis.inbound)}
```
{mermaid_docs}
---

# Tam Kaynak Arşivi

{source_blocks}
"""


def skill_content(module: ModuleInfo, analysis: ModuleAnalysis, module_map: dict[str, ModuleInfo]) -> str:
    return f"""# Skill: {module.name}

## Ana bileşen
- Sınıf: `{analysis.main_class}` in `{analysis.main_file}`
- Mission: {module.mission}

## API özeti
{bulletize([f"`{e.method} {e.path}` → `{e.handler}()` → {', '.join(e.calls) or '—'}" for e in analysis.endpoints[:10]])}

## Dış ilişkiler (neden)
{bulletize([f"→ [[{l.target_module}]] ({l.link_type}): {explain_outbound(module.name, l, module_map)}" for l in analysis.outbound[:10]])}

## Gelen ilişkiler (neden)
{bulletize([f"← [[{l.source_module}]] ({l.link_type}): {explain_inbound(module.name, l, module_map)}" for l in analysis.inbound[:10]])}

## Tam bilgi
`.sentrybot/obsidian/modules/{module.name}.md` ({analysis.file_count} dosya, {analysis.total_lines} satır)
"""


def sub_agent_content(module: ModuleInfo, analysis: ModuleAnalysis, module_map: dict[str, ModuleInfo]) -> str:
    return f"""# Sub-Agent: {module.name}-specialist

## Uzmanlık
`{analysis.main_class}` ve `{module.name}` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/{module.name}.md`

## Bileşen haritası
{bulletize([f"`{c.name}` — {c.doc or c.file}" for c in analysis.classes if "/services/" in c.file or c.name == analysis.main_class][:12])}

## Dış bağlantılar (neden)
{bulletize([f"[[{l.target_module}]] ({l.link_type}): {explain_outbound(module.name, l, module_map)}" for l in analysis.outbound[:12]])}

## Gelen bağlantılar (neden)
{bulletize([f"[[{l.source_module}]] ({l.link_type}): {explain_inbound(module.name, l, module_map)}" for l in analysis.inbound[:12]])}
"""


def write_index(path: Path, title: str, items: Iterable[str], prefix: str) -> None:
    lines = [f"# {title}", ""]
    for item in sorted(items):
        lines.append(f"- [{item}]({prefix}/{item}.md)")
    write_text(path, "\n".join(lines))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_obsidian_master_index(modules: list[ModuleInfo], analyses: dict[str, ModuleAnalysis]) -> None:
    lines = [
        "# SentryBOT Modül Bilgi Tabanı",
        "",
        "| Modül | Ana sınıf | Katman | Endpoint | Dış bağlantı | Gelen bağlantı |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for m in sorted(modules, key=lambda x: x.name):
        a = analyses[m.name]
        lines.append(
            f"| [[{m.name}]] | `{a.main_class or '—'}` | {m.layer} "
            f"| {len(a.endpoints)} | {len(a.outbound)} | {len(a.inbound)} |"
        )
    write_text(OBSIDIAN_MODULES_DIR / "INDEX.md", "\n".join(lines))


def main() -> None:
    registry_text = REGISTRY_PATH.read_text(encoding="utf-8")
    modules = parse_registry_modules(registry_text)
    if not modules:
        raise RuntimeError("No modules parsed")

    known_modules = {m.name for m in modules}
    module_map = {m.name: m for m in modules}

    module_map = {m.name: m for m in modules}

    analyses: dict[str, ModuleAnalysis] = {}
    for m in modules:
        analyses[m.name] = analyze_module(m.name, m, known_modules)

    for m in modules:
        analyses[m.name].inbound = scan_inbound_links(m.name, analyses, known_modules)

    for m in modules:
        a = analyses[m.name]
        write_text(OBSIDIAN_MODULES_DIR / f"{m.name}.md", obsidian_module_note(m, a, module_map))
        write_text(SKILLS_DIR / f"{m.name}.md", skill_content(m, a, module_map))
        write_text(SUB_AGENTS_DIR / f"{m.name}.md", sub_agent_content(m, a, module_map))
        print(f"  {m.name}: class={a.main_class}, endpoints={len(a.endpoints)}, "
              f"out={len(a.outbound)}, in={len(a.inbound)}, lines={a.total_lines}")

    names = [m.name for m in modules]
    write_index(SKILLS_DIR / "INDEX.md", "Module Skills", names, ".")
    write_index(SUB_AGENTS_DIR / "INDEX.md", "Sub-Agents", names, ".")
    write_obsidian_master_index(modules, analyses)
    print(f"\nDone: {len(modules)} modules with semantic knowledge base.")


if __name__ == "__main__":
    main()
