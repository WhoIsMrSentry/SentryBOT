from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

OUT_MD = ROOT / "PI_RUNTIME_PC_ONLY_ASSUMPTION_FOCUS_AUDIT.md"
OUT_JSON = ROOT / "pi_runtime_pc_only_assumption_focus_audit.json"

SCAN_ROOTS = ["modules", "apps", "services", "config"]
EXCLUDE_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".sentrybot_state", "node_modules", "dist", "build"}

PATTERNS = [
    ("windows_literal", re.compile(r"(?i)\bwindows\b")),
    ("sys_platform_win32", re.compile(r"sys\.platform\s*(?:==|!=|in)\s*[\"']win32[\"']")),
    ("os_name_nt", re.compile(r"os\.name\s*(?:==|!=)\s*[\"']nt[\"']")),
    ("platform_system_windows", re.compile(r"platform\.system\(\)\s*(?:==|!=)\s*[\"']Windows[\"']")),
    ("powershell", re.compile(r"(?i)\bpowershell\b")),
    ("dot_venv_scripts", re.compile(r"(?i)(?:\\.venv|Scripts[\\\\/]python\.exe|Scripts[\\\\/]pip\.exe)")),
    ("windows_drive_path", re.compile(r"[A-Za-z]:\\\\(?:Users|Program Files|Windows|Temp|tmp|Sentry|Project|[^\\s\"']+)")),
    ("onedrive_desktop_path", re.compile(r"(?i)(OneDrive|MasaÃ¼stÃ¼|Desktop)")),
    ("serial_com_port", re.compile(r"\bCOM\d+\b")),
    ("opencv_dshow_msmf", re.compile(r"\b(?:CAP_DSHOW|CAP_MSMF|DSHOW|MSMF)\b")),
    ("win32_api", re.compile(r"\b(?:win32api|win32gui|pywin32|ctypes\.windll|winsound|msvcrt)\b")),
    ("bat_cmd", re.compile(r"(?i)\b(?:cmd\.exe|\.bat|\.cmd)\b")),
]

BENIGN_CONTEXT_HINTS = [
    "docstring",
    "comment",
    "example",
    "docs",
    "readme",
    "test",
    "dev",
    "diagnostic",
    "audit",
    "fallback",
    "optional",
]

RUNTIME_CRITICAL_HINTS = [
    "camera",
    "capture",
    "speech",
    "speak",
    "wakeword",
    "gateway",
    "autonomy",
    "hardware",
    "arduino",
    "esp",
    "neopixel",
    "oled",
    "piservo",
    "vlm",
]


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDE_PARTS for part in path.parts)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def iter_files() -> list[Path]:
    suffixes = {".py", ".json", ".yml", ".yaml", ".md", ".toml", ".ini", ".service", ".sh"}
    out = []
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if root.exists():
            out.extend(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes and not should_skip(p))
    return sorted(set(out))


def line_kind(line: str) -> str:
    stripped = line.strip()
    triple_double = chr(34) * 3
    triple_single = chr(39) * 3
    if stripped.startswith("#"):
        return "comment"
    if stripped.startswith((triple_double, triple_single)) or stripped.endswith((triple_double, triple_single)):
        return "docstring_edge"
    return "code_or_text"


def ast_context(path: Path) -> dict[int, str]:
    if path.suffix.lower() != ".py":
        return {}
    try:
        tree = ast.parse(read_text(path))
    except Exception:
        return {}
    contexts: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if start and end:
                for n in range(start, end + 1):
                    contexts[n] = f"{type(node).__name__}:{node.name}"
    return contexts


def classify_hit(path_s: str, pattern_name: str, line: str, context: str) -> str:
    lower = f"{path_s} {line} {context}".lower()

    if path_s.startswith("config/"):
        return "config_review"
    if any(path_s.startswith(prefix) for prefix in ["tests/", "tools/", "scripts/"]):
        return "dev_only"

    if pattern_name in {"sys_platform_win32", "os_name_nt", "platform_system_windows"}:
        return "needs_review"

    if pattern_name in {"windows_drive_path", "dot_venv_scripts", "powershell", "bat_cmd", "win32_api"}:
        return "pi_blocker_candidate"

    if pattern_name == "opencv_dshow_msmf":
        if "_opencv_robot_backend_candidates" in context:
            return "needs_review"
        if "backend" in lower or "fallback" in lower or "auto" in lower or "windows-only" in lower:
            return "needs_review"
        return "pi_blocker_candidate"

    if pattern_name == "serial_com_port":
        if "example" in lower or "default" in lower or "fallback" in lower:
            return "needs_review"
        return "pi_blocker_candidate"

    if pattern_name == "windows_literal":
        if any(h in lower for h in BENIGN_CONTEXT_HINTS):
            return "benign_documentation"
        return "needs_review"

    if pattern_name == "onedrive_desktop_path":
        if any(h in lower for h in BENIGN_CONTEXT_HINTS):
            return "benign_documentation"
        return "pi_blocker_candidate"

    return "needs_review"


def snippets(lines: list[str], hit_line: int, radius: int = 2) -> str:
    start = max(1, hit_line - radius)
    end = min(len(lines), hit_line + radius)
    return "\n".join(f"{n:04d}: {lines[n-1]}" for n in range(start, end + 1))


def file_hits(path: Path) -> dict[str, Any] | None:
    text = read_text(path)
    lines = text.splitlines()
    ctx_by_line = ast_context(path)
    hits = []
    for idx, line in enumerate(lines, start=1):
        for name, pattern in PATTERNS:
            if not pattern.search(line):
                continue
            context = ctx_by_line.get(idx, "")
            severity = classify_hit(rel(path), name, line, context)
            hits.append({
                "line": idx,
                "pattern": name,
                "severity": severity,
                "kind": line_kind(line),
                "context": context,
                "text": line.strip()[:500],
                "snippet": snippets(lines, idx),
            })
    if not hits:
        return None
    path_s = rel(path)
    severities = Counter(h["severity"] for h in hits)
    return {
        "path": path_s,
        "lines": len(lines),
        "runtime_critical_hint": any(h in path_s.lower() for h in RUNTIME_CRITICAL_HINTS),
        "hit_count": len(hits),
        "severities": dict(severities),
        "patterns": sorted({h["pattern"] for h in hits}),
        "hits": hits,
    }


def table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("\n", "<br>")[:900] for x in row) + " |")
    return "\n".join(out)


files = iter_files()
records = [r for p in files if (r := file_hits(p))]
severity_counts = Counter()
pattern_counts = Counter()
for r in records:
    severity_counts.update(r["severities"])
    pattern_counts.update(r["patterns"])

blockers = [
    r for r in records
    if r["severities"].get("pi_blocker_candidate", 0) > 0 and r["runtime_critical_hint"]
]
review = [
    r for r in records
    if r["severities"].get("needs_review", 0) > 0 or r["severities"].get("config_review", 0) > 0
]
benign = [
    r for r in records
    if set(r["severities"].keys()).issubset({"benign_documentation", "dev_only"})
]

summary = {
    "target": "Pi/Linux robot runtime",
    "pc_is_dev_host_only": True,
    "files_scanned": len(files),
    "files_with_strict_pc_patterns": len(records),
    "runtime_blocker_candidate_files": len(blockers),
    "review_files": len(review),
    "benign_or_dev_only_files": len(benign),
    "severity_counts": dict(severity_counts),
    "pattern_counts": dict(pattern_counts),
}

data = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "report_type": "pi_runtime_pc_only_assumption_focus_audit",
    "summary": summary,
    "blocker_candidates": blockers,
    "review": review,
    "benign_or_dev_only": benign,
    "all_records": records,
    "recommended_next": [
        "Patch only blocker candidates that are in runtime-critical paths.",
        "Do not remove PC dev support from tools/tests; PC remains the development host.",
        "For camera backends, prefer Linux/Pi backend ordering: picamera2/libcamera/v4l2 first, OpenCV fallback second, Windows backends never as robot default.",
        "For serial defaults, robot profile should use /dev/serial/by-id, /dev/ttyACM*, or /dev/ttyUSB*, not COM ports.",
        "After focused cleanup, rerun Pi robot runtime refactor audit and full CI.",
    ],
}

md = [
    "# SentryBOT Pi Runtime PC-only Assumption Focus Audit",
    "",
    f"Generated: `{data['generated_at']}`",
    "",
    "Target: Pi/Linux robot runtime. PC remains only the development/test host.",
    "",
    "Report-only. No code changed and no hardware/camera/VLM/motion was started.",
    "",
    "This is a strict follow-up to the broad audit. It avoids broad false positives and focuses on real PC-only patterns.",
    "",
    "## Summary",
    "",
    table(["metric", "value"], [[k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v] for k, v in summary.items()]),
    "",
    "## Runtime Blocker Candidates",
    "",
]
if blockers:
    md.append(table(["path", "patterns", "severities", "hit_count"], [
        [r["path"], ", ".join(r["patterns"]), json.dumps(r["severities"], ensure_ascii=False), r["hit_count"]]
        for r in blockers
    ]))
    for r in blockers[:40]:
        md += ["", f"### `{r['path']}`", ""]
        for h in r["hits"][:10]:
            if h["severity"] == "pi_blocker_candidate":
                md += [f"Pattern: `{h['pattern']}` line `{h['line']}`", "", "```text", h["snippet"], "```", ""]
else:
    md.append("No runtime blocker candidates found.")
md += [
    "",
    "## Review Files",
    "",
]
if review:
    md.append(table(["path", "patterns", "severities", "hit_count"], [
        [r["path"], ", ".join(r["patterns"]), json.dumps(r["severities"], ensure_ascii=False), r["hit_count"]]
        for r in review[:160]
    ]))
else:
    md.append("No review files found.")
md += [
    "",
    "## Benign / Dev-only Files",
    "",
]
if benign:
    md.append(table(["path", "patterns", "severities", "hit_count"], [
        [r["path"], ", ".join(r["patterns"]), json.dumps(r["severities"], ensure_ascii=False), r["hit_count"]]
        for r in benign[:160]
    ]))
else:
    md.append("No benign/dev-only files found.")
md += ["", "## Recommended Next", ""]
for step in data["recommended_next"]:
    md.append(f"- {step}")
md.append("")

OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
OUT_MD.write_text("\n".join(md), encoding="utf-8")

print("[WRITE] PI_RUNTIME_PC_ONLY_ASSUMPTION_FOCUS_AUDIT.md")
print("[WRITE] pi_runtime_pc_only_assumption_focus_audit.json")
for k, v in summary.items():
    if isinstance(v, dict):
        print(f"[SUMMARY] {k}={json.dumps(v, ensure_ascii=False)}")
    else:
        print(f"[SUMMARY] {k}={v}")
print("[DONE] Pi runtime PC-only assumption focus audit complete")