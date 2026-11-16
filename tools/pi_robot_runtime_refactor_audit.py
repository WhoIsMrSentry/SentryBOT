from __future__ import annotations

import ast
import contextlib
import importlib
import io
import json
import os
import platform
import py_compile
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._audit_common import (  # noqa: E402
    VOICE_CONFIG_FILES,
    iter_repo_files,
    parse_output_dir_arg,
    read_text,
    rel as _common_rel,
    resolve_output_paths,
    safe_json,
    safe_yaml,
    summarize as summarize_config,
    table,
    write_audit_reports,
)

MD_NAME = "PI_ROBOT_RUNTIME_REFACTOR_AUDIT.md"
JSON_NAME = "pi_robot_runtime_refactor_audit.json"

SCAN_ROOTS = ["modules", "apps", "services", "scripts", "tools", "tests", "config"]

RUNTIME_PREFIXES = [
    "modules/",
    "apps/",
    "services/",
]

DEV_ONLY_PREFIXES = [
    "tests/",
    "tools/ci/",
    "tools/graph-ui/",
]

PI_TARGET_TERMS = [
    "raspberry",
    "linux",
    "aarch64",
    "arm",
    "/dev/",
    "/boot",
    "systemd",
    "udev",
    "gpio",
    "i2c",
    "serial",
    "ttyUSB",
    "ttyACM",
    "picamera2",
    "libcamera",
    "v4l2",
    "VideoCapture",
    "cv2",
    "sounddevice",
    "alsa",
    "pulseaudio",
    "piper",
    "speech_recognition",
    "openwakeword",
]

PC_ASSUMPTION_TERMS = [
    "Windows",
    "win32",
    "nt",
    "PowerShell",
    "powershell",
    ".venv",
    "Scripts\\\\python.exe",
    "Scripts/python.exe",
    "OneDrive",
    "MasaÃ¼stÃ¼",
    "C:\\\\",
    "COM",
    "MSMF",
    "DSHOW",
    "SENTRYBOT_PC_TEST",
    "allow_pc",
    "pc_dry_run",
    "PC",
]

STUB_TERMS = [
    "stub",
    "fake",
    "dummy",
    "mock",
    "legacy",
    "deprecated",
    "fallback",
]

STARTUP_SIDE_EFFECT_TERMS = [
    "print(",
    "Console(",
    "Runtime console initialized",
    "start(",
    "start_background(",
    "VideoCapture(",
    "serial.Serial(",
    "subprocess.Popen(",
    "uvicorn.run(",
]

CRITICAL_IMPORT_MODULES = [
    "modules.gateway.services.bootstrap",
    "modules.autonomy.services.brain",
    "modules.autonomy.services.robot_capability_map",
    "modules.camera.api.router",
    "modules.camera.services.capture",
    "modules.camera.services.imx500_runner",
    "modules.vlm_bridge.services.processor",
    "modules.voice.speech.xSpeechService",
    "modules.voice.speak.xSpeakService",
    "modules.voice.wakeword.xWakewordService",
    "modules.expression.semantic.services.output_bridge",
]

CONFIG_FILES = [
    "config/robot_capability_registry.json",
    "config/robot_execution_profiles.json",
    "config/robot_arm_policy.json",
    "modules/camera/config/config.yml",
    "modules/vlm_bridge/config/config.yml",
    *VOICE_CONFIG_FILES,
]


def rel(path: Path) -> str:
    return _common_rel(path, ROOT)


def is_runtime_path(path_s: str) -> bool:
    return any(path_s.startswith(prefix) for prefix in RUNTIME_PREFIXES)


def is_dev_only_path(path_s: str) -> bool:
    return any(path_s.startswith(prefix) for prefix in DEV_ONLY_PREFIXES)


def iter_files() -> list[Path]:
    return iter_repo_files(ROOT, SCAN_ROOTS)


def route_from_dec(dec: ast.AST) -> str | None:
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    method = None
    if isinstance(func, ast.Attribute) and func.attr in {"get", "post", "put", "delete", "patch", "websocket"}:
        method = func.attr.upper()
    elif isinstance(func, ast.Name) and func.id in {"get", "post", "put", "delete", "patch"}:
        method = func.id.upper()
    if method and dec.args and isinstance(dec.args[0], ast.Constant):
        return f"{method} {dec.args[0].value}"
    return method


def parse_py(path: Path, text: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "compile_ok": None,
        "compile_error": None,
        "classes": [],
        "functions": [],
        "routes": [],
        "imports": [],
        "from_imports": [],
        "top_level_calls": [],
        "platform_checks": [],
    }
    try:
        py_compile.compile(str(path), doraise=True)
        item["compile_ok"] = True
    except Exception as exc:
        item["compile_ok"] = False
        item["compile_error"] = str(exc)
        return item

    try:
        tree = ast.parse(text)
    except Exception as exc:
        item["ast_error"] = str(exc)
        return item

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                item["imports"].append({"name": a.name, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            item["from_imports"].append({"module": node.module or "", "names": [a.name for a in node.names], "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            item["classes"].append({"name": node.name, "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            item["functions"].append({"name": node.name, "line": node.lineno})
            for dec in node.decorator_list:
                route = route_from_dec(dec)
                if route:
                    item["routes"].append({"route": route, "function": node.name, "line": node.lineno})
        elif isinstance(node, ast.Call):
            try:
                call_s = ast.unparse(node)
            except Exception:
                call_s = ""
            if any(term in call_s for term in ["platform.", "os.name", "sys.platform", "getenv", "environ"]):
                item["platform_checks"].append({"line": getattr(node, "lineno", None), "call": call_s[:240]})

    for node in tree.body:
        try:
            code_s = ast.unparse(node)
        except Exception:
            code_s = ""
        if isinstance(node, (ast.Expr, ast.Assign, ast.AnnAssign, ast.With, ast.Try)):
            if any(term in code_s for term in STARTUP_SIDE_EFFECT_TERMS):
                item["top_level_calls"].append({"line": getattr(node, "lineno", None), "code": code_s[:360]})
    return item


def file_record(path: Path) -> dict[str, Any]:
    path_s = rel(path)
    text = read_text(path)
    low = text.lower()
    rec: dict[str, Any] = {
        "path": path_s,
        "suffix": path.suffix.lower(),
        "runtime_path": is_runtime_path(path_s),
        "dev_only_path": is_dev_only_path(path_s),
        "lines": text.count("\n") + 1,
        "pi_target_hits": sorted({t for t in PI_TARGET_TERMS if t.lower() in low or t.lower() in path_s.lower()}),
        "pc_assumption_hits": sorted({t for t in PC_ASSUMPTION_TERMS if t.lower() in low or t.lower() in path_s.lower()}),
        "stub_hits": sorted({t for t in STUB_TERMS if t.lower() in low or t.lower() in path_s.lower()}),
    }
    if path.suffix.lower() == ".py":
        rec.update(parse_py(path, text))
    return rec


def config_records() -> list[dict[str, Any]]:
    rows = []
    for name in CONFIG_FILES:
        path = ROOT / name
        item: dict[str, Any] = {"path": name, "exists": path.exists()}
        if path.exists():
            item["lines"] = read_text(path).count("\n") + 1
            if path.suffix.lower() == ".json":
                data = safe_json(path)
                item["summary"] = summarize_config(data)
                item["raw"] = data
            elif path.suffix.lower() in {".yml", ".yaml"}:
                data = safe_yaml(path)
                item["summary"] = summarize_config(data)
                item["raw"] = data
        rows.append(item)
    return rows


def import_side_effect_probe(module_name: str) -> dict[str, Any]:
    os.environ.setdefault("SENTRYBOT_DISABLE_AUTOSTART", "true")
    os.environ.setdefault("SENTRYBOT_PC_TEST", "1")
    os.environ.setdefault("SENTRYBOT_PI_RUNTIME_AUDIT", "1")
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            module = importlib.import_module(module_name)
        return {
            "module": module_name,
            "ok": True,
            "stdout_len": len(stdout_buf.getvalue()),
            "stderr_len": len(stderr_buf.getvalue()),
            "stdout_preview": stdout_buf.getvalue()[:1200],
            "stderr_preview": stderr_buf.getvalue()[:1200],
            "has_get_router": hasattr(module, "get_router"),
            "has_status": hasattr(module, "status"),
        }
    except Exception as exc:
        return {
            "module": module_name,
            "ok": False,
            "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-10:],
            "stdout_len": len(stdout_buf.getvalue()),
            "stderr_len": len(stderr_buf.getvalue()),
            "stdout_preview": stdout_buf.getvalue()[:1200],
            "stderr_preview": stderr_buf.getvalue()[:1200],
        }


def snippet(path: Path, terms: list[str], radius: int = 2, limit: int = 8) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = read_text(path).splitlines()
    hits = []
    for idx, line in enumerate(lines, start=1):
        if any(term.lower() in line.lower() for term in terms):
            hits.append(idx)
    ranges = []
    for hit in hits:
        start = max(1, hit - radius)
        end = min(len(lines), hit + radius)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    out = []
    for start, end in ranges[:limit]:
        out.append({
            "start": start,
            "end": end,
            "text": "\n".join(f"{n:04d}: {lines[n-1]}" for n in range(start, end + 1)),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    output_dir = parse_output_dir_arg(argv, description="Pi robot runtime refactor audit")
    out_md, out_json = resolve_output_paths(ROOT, output_dir, MD_NAME, JSON_NAME)

    all_records = [file_record(p) for p in iter_files()]

    runtime_pc_assumptions = [
        r for r in all_records
        if r["runtime_path"] and r["pc_assumption_hits"]
    ]
    runtime_stubs = [
        r for r in all_records
        if r["runtime_path"] and r["stub_hits"]
    ]
    runtime_pi_touchpoints = [
        r for r in all_records
        if r["runtime_path"] and r["pi_target_hits"]
    ]
    compile_failures = [
        r for r in all_records
        if r.get("compile_ok") is False and r["path"].endswith(".py")
    ]
    runtime_top_level_side_effects = [
        r for r in all_records
        if r["runtime_path"] and r.get("top_level_calls")
    ]

    configs = config_records()
    imports = [import_side_effect_probe(m) for m in CRITICAL_IMPORT_MODULES]
    import_failures = [r for r in imports if not r["ok"]]
    import_stdout_side_effects = [r for r in imports if r.get("stdout_len", 0) > 0 or r.get("stderr_len", 0) > 0]

    config_findings = []
    for cfg in configs:
        raw = cfg.get("raw")
        if cfg["path"] == "config/robot_execution_profiles.json" and isinstance(raw, dict):
            active_mode = raw.get("active_mode")
            if active_mode == "pc_dry_run":
                config_findings.append({
                    "severity": "needs_pi_profile_plan",
                    "path": cfg["path"],
                    "finding": "active_mode is pc_dry_run; Pi deployment needs robot_safe_preview/manual profile selection, not PC default.",
                })
        if cfg["path"] == "config/robot_capability_registry.json" and isinstance(raw, dict):
            profile = raw.get("profile")
            if profile == "pc_dry_run":
                config_findings.append({
                    "severity": "needs_pi_profile_plan",
                    "path": cfg["path"],
                    "finding": "capability registry profile is pc_dry_run; robot target needs explicit deployment mode without enabling hardware by default.",
                })
        if cfg["path"] == "modules/camera/config/config.yml" and isinstance(raw, dict):
            if raw.get("enabled") is False:
                config_findings.append({
                    "severity": "safe_default",
                    "path": cfg["path"],
                    "finding": "camera.enabled is false; safe for refactor, activation requires separate robot profile.",
                })

    summary = {
        "files_scanned": len(all_records),
        "compile_failures": len(compile_failures),
        "runtime_pc_assumption_files": len(runtime_pc_assumptions),
        "runtime_stub_files": len(runtime_stubs),
        "runtime_pi_touchpoint_files": len(runtime_pi_touchpoints),
        "runtime_top_level_side_effect_files": len(runtime_top_level_side_effects),
        "critical_imports": len(imports),
        "critical_import_failures": len(import_failures),
        "critical_import_stdout_side_effects": len(import_stdout_side_effects),
        "config_findings": len(config_findings),
        "host_platform": f"{platform.system()} {platform.machine()}",
        "audit_target": "Pi/Linux robot runtime",
    }

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_type": "pi_robot_runtime_refactor_audit",
        "pc_is_dev_host_only": True,
        "target": "Raspberry Pi / Linux robot runtime",
        "summary": summary,
        "compile_failures": compile_failures,
        "runtime_pc_assumptions": runtime_pc_assumptions,
        "runtime_stubs": runtime_stubs,
        "runtime_pi_touchpoints": runtime_pi_touchpoints,
        "runtime_top_level_side_effects": runtime_top_level_side_effects,
        "critical_import_probes": imports,
        "config_records": configs,
        "config_findings": config_findings,
        "snippets": {
            "gateway_bootstrap_pc_terms": snippet(ROOT / "modules/gateway/services/bootstrap.py", PC_ASSUMPTION_TERMS + ["SENTRYBOT_DISABLE_AUTOSTART", "on_event"], limit=10),
            "robot_profiles": snippet(ROOT / "config/robot_execution_profiles.json", ["pc_dry_run", "robot_safe_preview", "robot_safe_manual"], limit=10),
            "camera_config": snippet(ROOT / "modules/camera/config/config.yml", ["enabled", "backend", "source", "picamera2", "opencv", "imx500"], limit=10),
        },
        "recommended_next": [
            "Create a Pi deployment profile plan instead of using pc_dry_run as the runtime target.",
            "Clean or gate import-time console side effects so imports stay quiet on robot runtime.",
            "Separate PC-only tools from robot runtime modules; PC-only findings should not drive robot design.",
            "Inspect runtime stub/legacy files by caller before deleting or replacing.",
            "After audit decisions, patch only robot-target code paths, then run existing CI.",
        ],
    }

    md = [
        "# SentryBOT Pi Robot Runtime Refactor Audit",
        "",
        f"Generated: `{data['generated_at']}`",
        "",
        "Target: Raspberry Pi / Linux robot runtime. PC is only the development/test host.",
        "",
        "Report-only. No code was changed and no hardware/camera/VLM/motion was started.",
        "",
        "## Summary",
        "",
        table(["metric", "value"], [[k, v] for k, v in summary.items()]),
        "",
        "## Key Decision",
        "",
        "Continue refactor for Pi/Linux robot runtime. Do not optimize architecture around Windows/PC behavior.",
        "",
        "## Config Findings",
        "",
    ]
    if config_findings:
        md.append(table(["severity", "path", "finding"], [[x["severity"], x["path"], x["finding"]] for x in config_findings]))
    else:
        md.append("No config findings.")
    md += [
        "",
        "## Critical Import Probes",
        "",
        table(["module", "ok", "stdout_len", "stderr_len", "stdout_preview/error"], [
            [
                r["module"],
                r["ok"],
                r.get("stdout_len"),
                r.get("stderr_len"),
                (r.get("stdout_preview") or r.get("error") or "")[:650],
            ]
            for r in imports
        ]),
        "",
        "## Runtime PC Assumption Files",
        "",
    ]
    if runtime_pc_assumptions:
        md.append(table(["path", "hits", "lines"], [[r["path"], ", ".join(r["pc_assumption_hits"]), r["lines"]] for r in runtime_pc_assumptions[:160]]))
    else:
        md.append("No runtime PC assumption files found.")
    md += [
        "",
        "## Runtime Stub / Legacy / Fallback Files",
        "",
    ]
    if runtime_stubs:
        md.append(table(["path", "hits", "lines"], [[r["path"], ", ".join(r["stub_hits"]), r["lines"]] for r in runtime_stubs[:160]]))
    else:
        md.append("No runtime stub/legacy/fallback files found.")
    md += [
        "",
        "## Runtime Pi Touchpoint Files",
        "",
    ]
    if runtime_pi_touchpoints:
        md.append(table(["path", "pi_hits", "pc_hits", "lines"], [[r["path"], ", ".join(r["pi_target_hits"]), ", ".join(r["pc_assumption_hits"]), r["lines"]] for r in runtime_pi_touchpoints[:180]]))
    else:
        md.append("No Pi touchpoint files found.")
    md += [
        "",
        "## Runtime Top-level Side-effect Candidates",
        "",
    ]
    if runtime_top_level_side_effects:
        md.append(table(["path", "top_level_calls"], [
            [r["path"], json.dumps(r.get("top_level_calls", [])[:5], ensure_ascii=False)]
            for r in runtime_top_level_side_effects[:120]
        ]))
    else:
        md.append("No runtime top-level side-effect candidates found.")
    md += [
        "",
        "## Compile Failures",
        "",
    ]
    if compile_failures:
        md.append(table(["path", "error"], [[r["path"], r.get("compile_error", "")] for r in compile_failures]))
    else:
        md.append("No compile failures.")
    md += [
        "",
        "## Key Snippets",
        "",
    ]
    for name, items in data["snippets"].items():
        md += [f"### {name}", ""]
        if items:
            for s in items:
                md += ["```text", s["text"], "```", ""]
        else:
            md += ["No snippets.", ""]
    md += ["## Recommended Next", ""]
    for step in data["recommended_next"]:
        md.append(f"- {step}")
    md.append("")

    write_audit_reports(out_md, out_json, md, data)

    print(f"[WRITE] {rel(out_md) if out_md.is_relative_to(ROOT) else out_md}")
    print(f"[WRITE] {rel(out_json) if out_json.is_relative_to(ROOT) else out_json}")
    for k, v in summary.items():
        print(f"[SUMMARY] {k}={v}")
    print("[DONE] Pi robot runtime refactor audit complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())