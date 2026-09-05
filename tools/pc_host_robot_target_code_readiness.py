from __future__ import annotations

import ast
import importlib
import json
import os
import platform
import py_compile
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path.cwd()

# Ensure project root is importable when this tool is executed from tools/.
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

OUT_MD = ROOT / "PC_HOST_ROBOT_TARGET_CODE_READINESS.md"
OUT_JSON = ROOT / "pc_host_robot_target_code_readiness.json"

SAFE_ENV = {
    "SENTRYBOT_DISABLE_AUTOSTART": "true",
    "SENTRYBOT_PC_TEST": "1",
    "SENTRYBOT_ROBOT_TARGET_CODE_AUDIT": "1",
}

ROBOT_CRITICAL_FILES = [
    "modules/gateway/services/bootstrap.py",
    "modules/autonomy/services/robot_capability_map.py",
    "modules/autonomy/services/companion_goal_executor.py",
    "modules/autonomy/services/companion_auto_execute_gate.py",
    "modules/autonomy/services/companion_goal_selector.py",
    "modules/autonomy/services/companion_behavior_loop.py",
    "modules/camera/api/router.py",
    "modules/camera/services/capture.py",
    "modules/camera/services/imx500_runner.py",
    "modules/camera/services/onsensor_bus.py",
    "modules/vlm_bridge/api/router.py",
    "modules/vlm_bridge/services/processor.py",
    "modules/vlm_bridge/services/llm_client.py",
    "modules/expression/services/output_bridge.py",
    "modules/speech/xSpeechService.py",
    "modules/speak/xSpeakService.py",
    "modules/wakeword/xWakewordService.py",
    "tools/robot_runtime_gateway_status_probe.py",
    "tools/robot_capability_probe.py",
    "tools/robot_hardware_gap_report.py",
    "tools/robot_arm_control.py",
    "tools/ci/robot_safety_ci_guard.py",
    "tools/ci/robot_safe_manual_gate.py",
]

ROBOT_CRITICAL_MODULES = [
    "modules.gateway.services.bootstrap",
    "modules.autonomy.services.robot_capability_map",
    "modules.autonomy.services.companion_goal_executor",
    "modules.autonomy.services.companion_auto_execute_gate",
    "modules.autonomy.services.companion_goal_selector",
    "modules.autonomy.services.companion_behavior_loop",
    "modules.camera.api.router",
    "modules.camera.services.capture",
    "modules.camera.services.imx500_runner",
    "modules.camera.services.onsensor_bus",
    "modules.vlm_bridge.api.router",
    "modules.vlm_bridge.services.processor",
    "modules.vlm_bridge.services.llm_client",
    "modules.expression.semantic.services.output_bridge",
    "modules.voice.speech.xSpeechService",
    "modules.voice.speak.xSpeakService",
    "modules.voice.wakeword.xWakewordService",
]

CONFIG_FILES = [
    "config/robot_capability_registry.json",
    "config/robot_execution_profiles.json",
    "config/robot_arm_policy.json",
    "modules/camera/config/config.yml",
    "modules/vlm_bridge/config/config.yml",
    "modules/speak/config/config.yml",
    "modules/speech/config/config.yml",
    "modules/wakeword/config/config.yml",
]

DANGEROUS_CALLS = [
    "VideoCapture",
    ".start(",
    ".start_background(",
    "subprocess.Popen",
    "serial.Serial",
    "gpiozero",
    "RPi.GPIO",
    "lgpio",
    "pigpio",
    "smbus",
    "smbus2",
]

ROBOT_TERMS = [
    "hardware_enabled",
    "armed",
    "dry_run",
    "robot_safe",
    "capability",
    "camera",
    "vlm",
    "speech",
    "wakeword",
    "neopixel",
    "oled",
    "servo",
    "arduino",
    "esp",
]


@dataclass
class Case:
    name: str
    status: str
    reason: str


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def safe_json(path: Path) -> Any:
    try:
        return json.loads(read_text(path))
    except Exception as exc:
        return {"_error": str(exc)}


def safe_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        return {"_yaml_available": False, "_error": str(exc)}
    try:
        return yaml.safe_load(read_text(path))
    except Exception as exc:
        return {"_yaml_available": True, "_error": str(exc)}


def summarize(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:60]:
            if isinstance(item, dict):
                out[str(key)] = {"type": "object", "keys": list(item.keys())[:24], "count": len(item)}
            elif isinstance(item, list):
                out[str(key)] = {"type": "list", "count": len(item)}
            else:
                out[str(key)] = item
        return out
    if isinstance(value, list):
        return {"type": "list", "count": len(value), "sample": value[:8]}
    return value


def parse_file(path: Path) -> dict[str, Any]:
    item: dict[str, Any] = {"path": rel(path), "exists": path.exists()}
    if not path.exists():
        return item
    text = read_text(path)
    item["lines"] = text.count("\n") + 1
    item["robot_terms"] = sorted({term for term in ROBOT_TERMS if term in text})
    item["dangerous_call_text_hits"] = sorted({term for term in DANGEROUS_CALLS if term in text})
    item["top_level_dangerous_calls"] = []
    item["routes"] = []
    if path.suffix.lower() != ".py":
        return item
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

    for node in tree.body:
        call = None
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
        if call is not None:
            try:
                call_text = ast.unparse(call)
            except Exception:
                call_text = ""
            if any(term in call_text for term in DANGEROUS_CALLS):
                item["top_level_dangerous_calls"].append({"line": getattr(node, "lineno", None), "call": call_text[:240]})

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                method = None
                if isinstance(func, ast.Attribute) and func.attr in {"get", "post", "put", "delete", "patch"}:
                    method = func.attr.upper()
                if method:
                    route_path = ""
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        route_path = str(dec.args[0].value)
                    item["routes"].append({"method": method, "path": route_path, "function": node.name, "line": node.lineno})
    return item


def import_probe(module_name: str) -> dict[str, Any]:
    started = datetime.now()
    try:
        module = importlib.import_module(module_name)
        attrs = {
            "has_get_router": hasattr(module, "get_router"),
            "has_status": hasattr(module, "status"),
            "has_load_config": hasattr(module, "load_config"),
        }
        if module_name.endswith("robot_capability_map"):
            try:
                attrs["robot_capability_status"] = module.status(ROOT)  # type: ignore[attr-defined]
            except Exception as exc:
                attrs["robot_capability_status_error"] = str(exc)
        return {
            "module": module_name,
            "ok": True,
            "attrs": attrs,
            "elapsed_ms": round((datetime.now() - started).total_seconds() * 1000, 1),
        }
    except Exception as exc:
        return {
            "module": module_name,
            "ok": False,
            "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-8:],
            "elapsed_ms": round((datetime.now() - started).total_seconds() * 1000, 1),
        }


def config_probe() -> list[dict[str, Any]]:
    rows = []
    for name in CONFIG_FILES:
        path = ROOT / name
        item: dict[str, Any] = {"path": name, "exists": path.exists()}
        if path.exists():
            item["lines"] = read_text(path).count("\n") + 1
            if path.suffix.lower() == ".json":
                item["summary"] = summarize(safe_json(path))
            elif path.suffix.lower() in {".yml", ".yaml"}:
                item["summary"] = summarize(safe_yaml(path))
        rows.append(item)
    return rows


def platform_probe() -> dict[str, Any]:
    return {
        "host_system": platform.system(),
        "host_machine": platform.machine(),
        "host_release": platform.release(),
        "python": sys.version.split()[0],
        "mode": "PC host validating robot-target code",
        "robot_target_available_now": False,
    }


def table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("\n", "<br>")[:600] for x in row) + " |")
    return "\n".join(out)


def main() -> int:
    os.environ.update(SAFE_ENV)

    file_records = [parse_file(ROOT / name) for name in ROBOT_CRITICAL_FILES]
    imports = [import_probe(name) for name in ROBOT_CRITICAL_MODULES]
    configs = config_probe()
    platform_info = platform_probe()

    cases: list[Case] = []

    missing_files = [r["path"] for r in file_records if not r.get("exists")]
    cases.append(Case("critical_files_present", "PASS" if not missing_files else "FAIL", ", ".join(missing_files) if missing_files else "all present"))

    compile_fail = [r["path"] for r in file_records if r.get("exists") and r.get("compile_ok") is False]
    cases.append(Case("critical_files_compile", "PASS" if not compile_fail else "FAIL", ", ".join(compile_fail) if compile_fail else "all compile"))

    import_fail = [r["module"] for r in imports if not r.get("ok")]
    cases.append(Case("safe_imports_no_autostart", "PASS" if not import_fail else "FAIL", ", ".join(import_fail) if import_fail else "all imports ok"))

    top_level_danger = [
        f"{r['path']}:{x['line']}"
        for r in file_records
        for x in r.get("top_level_dangerous_calls", [])
    ]
    cases.append(Case("no_top_level_hardware_starts", "PASS" if not top_level_danger else "FAIL", ", ".join(top_level_danger) if top_level_danger else "none found"))

    config_missing = [r["path"] for r in configs if not r.get("exists")]
    cases.append(Case("robot_configs_present", "PASS" if not config_missing else "FAIL", ", ".join(config_missing) if config_missing else "all present"))

    cap_status = next((r.get("attrs", {}).get("robot_capability_status") for r in imports if r["module"].endswith("robot_capability_map")), None)
    safe_cap = isinstance(cap_status, dict) and cap_status.get("read_only") is True and cap_status.get("armed") is False and cap_status.get("hardware_enabled") is False
    cases.append(Case("capability_adapter_safe_defaults", "PASS" if safe_cap else "FAIL", json.dumps(cap_status, ensure_ascii=False)[:500]))

    failures = [c for c in cases if c.status != "PASS"]

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_type": "pc_host_robot_target_code_readiness",
        "intent": "Run on PC, validate code is robot-target-ready without requiring robot hardware.",
        "safe_env": SAFE_ENV,
        "platform": platform_info,
        "cases": [c.__dict__ for c in cases],
        "overall_ok": not failures,
        "file_records": file_records,
        "import_probes": imports,
        "config_records": configs,
        "recommended_next": [
            "Fix any FAIL cases before real robot deployment.",
            "Do not treat PC missing /dev devices as blocker in this audit.",
            "After code readiness is PASS, do gateway app factory/import status test on PC.",
            "Then create reversible camera start/stop plan, still guarded by robot profiles.",
        ],
    }

    md = [
        "# SentryBOT PC-host Robot-target Code Readiness",
        "",
        f"Generated: `{data['generated_at']}`",
        "",
        "Purpose: run on PC, validate code paths are suitable for robot runtime without needing robot hardware.",
        "",
        "This audit does not start camera, VLM, serial, GPIO, I2C, motion, or hardware.",
        "",
        "## Overall",
        "",
        table(["field", "value"], [
            ["overall_ok", data["overall_ok"]],
            ["host_system", platform_info["host_system"]],
            ["host_machine", platform_info["host_machine"]],
            ["robot_target_available_now", False],
        ]),
        "",
        "## Cases",
        "",
        table(["case", "status", "reason"], [[c.name, c.status, c.reason] for c in cases]),
        "",
        "## Import Probes",
        "",
        table(["module", "ok", "elapsed_ms", "attrs/error"], [
            [r["module"], r["ok"], r.get("elapsed_ms"), json.dumps(r.get("attrs", r.get("error", "")), ensure_ascii=False)]
            for r in imports
        ]),
        "",
        "## Critical Files",
        "",
        table(["path", "exists", "compile_ok", "lines", "robot_terms", "top_level_danger"], [
            [
                r["path"],
                r.get("exists"),
                r.get("compile_ok", ""),
                r.get("lines", ""),
                ", ".join(r.get("robot_terms", [])),
                json.dumps(r.get("top_level_dangerous_calls", []), ensure_ascii=False),
            ]
            for r in file_records
        ]),
        "",
        "## Configs",
        "",
        table(["path", "exists", "lines", "summary"], [
            [r["path"], r.get("exists"), r.get("lines", ""), json.dumps(r.get("summary", {}), ensure_ascii=False)]
            for r in configs
        ]),
        "",
        "## Recommended Next",
        "",
    ]
    for step in data["recommended_next"]:
        md.append(f"- {step}")
    md.append("")

    OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print("[WRITE] PC_HOST_ROBOT_TARGET_CODE_READINESS.md")
    print("[WRITE] pc_host_robot_target_code_readiness.json")
    for c in cases:
        print(f"[CASE] {c.name}={c.status} {c.reason}")
    print(f"[SUMMARY] overall_ok={data['overall_ok']}")
    print("[DONE] PC-host robot-target code readiness audit complete")
    return 0 if data["overall_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())