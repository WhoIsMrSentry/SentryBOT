from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import py_compile
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

OUT_MD = ROOT / "PI_IMPORT_TIME_SIDE_EFFECT_AUDIT.md"
OUT_JSON = ROOT / "pi_import_time_side_effect_audit.json"

SAFE_ENV = {
    "SENTRYBOT_DISABLE_AUTOSTART": "true",
    "SENTRYBOT_PI_RUNTIME_AUDIT": "1",
    "SENTRYBOT_RUNTIME_TARGET": "pi",
}

CRITICAL_MODULES = [
    "modules.gateway.services.bootstrap",
    "modules.autonomy.services.brain",
    "modules.autonomy.services.robot_runtime_profile",
    "modules.autonomy.services.robot_capability_map",
    "modules.autonomy.services.companion_goal_executor",
    "modules.autonomy.services.companion_auto_execute_gate",
    "modules.camera.api.router",
    "modules.camera.services.capture",
    "modules.camera.services.imx500_runner",
    "modules.vlm_bridge.api.router",
    "modules.vlm_bridge.services.processor",
    "modules.expression.services.output_bridge",
    "modules.speech.xSpeechService",
    "modules.speak.xSpeakService",
    "modules.wakeword.xWakewordService",
]

SEARCH_TERMS = [
    "SENTRYBOT RUNTIME",
    "Runtime console initialized",
    "Console(",
    "Panel(",
    "print(",
    "rich",
    "startup",
    "banner",
    "dashboard",
    "runtime console",
]


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def iter_runtime_py() -> list[Path]:
    roots = [ROOT / "modules", ROOT / "apps", ROOT / "services"]
    out = []
    for root in roots:
        if root.exists():
            out.extend(
                p for p in root.rglob("*.py")
                if ".venv" not in p.parts
                and "__pycache__" not in p.parts
            )
    return sorted(set(out))


def compile_runtime() -> list[dict[str, Any]]:
    failures = []
    for path in iter_runtime_py():
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            failures.append({"path": rel(path), "error": str(exc)})
    return failures


def import_probe(module_name: str) -> dict[str, Any]:
    os.environ.update(SAFE_ENV)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    before_modules = set(sys.modules)
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            module = importlib.import_module(module_name)
        after_modules = set(sys.modules)
        new_modules = sorted(m for m in after_modules - before_modules if m.startswith("modules."))
        return {
            "module": module_name,
            "ok": True,
            "stdout_len": len(stdout_buf.getvalue()),
            "stderr_len": len(stderr_buf.getvalue()),
            "stdout_preview": stdout_buf.getvalue()[:3000],
            "stderr_preview": stderr_buf.getvalue()[:3000],
            "new_project_modules": new_modules[:120],
            "new_project_modules_count": len(new_modules),
            "has_get_router": hasattr(module, "get_router"),
            "has_status": hasattr(module, "status"),
        }
    except Exception as exc:
        after_modules = set(sys.modules)
        new_modules = sorted(m for m in after_modules - before_modules if m.startswith("modules."))
        return {
            "module": module_name,
            "ok": False,
            "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-12:],
            "stdout_len": len(stdout_buf.getvalue()),
            "stderr_len": len(stderr_buf.getvalue()),
            "stdout_preview": stdout_buf.getvalue()[:3000],
            "stderr_preview": stderr_buf.getvalue()[:3000],
            "new_project_modules": new_modules[:120],
            "new_project_modules_count": len(new_modules),
        }


def candidate_files() -> list[dict[str, Any]]:
    records = []
    for path in iter_runtime_py():
        text = read_text(path)
        low = text.lower()
        hits = [term for term in SEARCH_TERMS if term.lower() in low]
        if not hits:
            continue
        lines = text.splitlines()
        snippets = []
        hit_lines = []
        for idx, line in enumerate(lines, start=1):
            if any(term.lower() in line.lower() for term in SEARCH_TERMS):
                hit_lines.append(idx)
        ranges = []
        for line_no in hit_lines:
            start = max(1, line_no - 3)
            end = min(len(lines), line_no + 3)
            if ranges and start <= ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
        for start, end in ranges[:8]:
            snippets.append({
                "start": start,
                "end": end,
                "text": "\n".join(f"{n:04d}: {lines[n-1]}" for n in range(start, end + 1)),
            })
        records.append({
            "path": rel(path),
            "hits": hits,
            "lines": len(lines),
            "snippets": snippets,
        })
    return records


def table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("\n", "<br>")[:900] for x in row) + " |")
    return "\n".join(out)


def main() -> int:
    compile_failures = compile_runtime()
    probes = [import_probe(name) for name in CRITICAL_MODULES]
    noisy = [p for p in probes if p.get("stdout_len", 0) > 0 or p.get("stderr_len", 0) > 0]
    failed = [p for p in probes if not p.get("ok")]
    candidates = candidate_files()

    summary = {
        "compile_failures": len(compile_failures),
        "critical_imports": len(probes),
        "critical_import_failures": len(failed),
        "noisy_imports": len(noisy),
        "candidate_files": len(candidates),
        "target": "Pi/Linux robot runtime",
        "report_only": True,
    }

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_type": "pi_import_time_side_effect_audit",
        "pc_is_dev_host_only": True,
        "target": "Pi/Linux robot runtime",
        "safe_env": SAFE_ENV,
        "summary": summary,
        "compile_failures": compile_failures,
        "import_probes": probes,
        "noisy_imports": noisy,
        "candidate_files": candidates,
        "recommended_next": [
            "Patch only the exact noisy import source.",
            "Do not remove runtime banner completely; only prevent import-time banner output.",
            "Runtime startup may still show banner when an app/CLI explicitly starts the console.",
            "After patch, re-run this audit and full CI.",
        ],
    }

    md = [
        "# SentryBOT Pi Import-time Side-effect Audit",
        "",
        f"Generated: `{data['generated_at']}`",
        "",
        "Target: Pi/Linux robot runtime. PC is only the dev/test host.",
        "",
        "Report-only. No code changed and no hardware/camera/VLM/motion started.",
        "",
        "Goal: imports must be quiet; startup banner may exist only during explicit runtime start.",
        "",
        "## Summary",
        "",
        table(["metric", "value"], [[k, v] for k, v in summary.items()]),
        "",
        "## Noisy Imports",
        "",
    ]
    if noisy:
        md.append(table(["module", "ok", "stdout_len", "stderr_len", "stdout_preview", "new_project_modules_count"], [
            [
                p["module"],
                p.get("ok"),
                p.get("stdout_len"),
                p.get("stderr_len"),
                p.get("stdout_preview", "")[:850],
                p.get("new_project_modules_count"),
            ]
            for p in noisy
        ]))
    else:
        md.append("No noisy imports found.")
    md += [
        "",
        "## Import Probes",
        "",
        table(["module", "ok", "stdout_len", "stderr_len", "new_project_modules_count", "error"], [
            [
                p["module"],
                p.get("ok"),
                p.get("stdout_len"),
                p.get("stderr_len"),
                p.get("new_project_modules_count"),
                p.get("error", ""),
            ]
            for p in probes
        ]),
        "",
        "## Candidate Files Containing Banner/Console Terms",
        "",
    ]
    if candidates:
        md.append(table(["path", "hits", "lines"], [
            [c["path"], ", ".join(c["hits"]), c["lines"]]
            for c in candidates[:160]
        ]))
        for c in candidates[:30]:
            md += ["", f"### `{c['path']}`", ""]
            for s in c.get("snippets", [])[:4]:
                md += ["```text", s["text"], "```", ""]
    else:
        md.append("No candidate files found.")
    md += [
        "",
        "## Compile Failures",
        "",
    ]
    if compile_failures:
        md.append(table(["path", "error"], [[x["path"], x["error"]] for x in compile_failures]))
    else:
        md.append("No compile failures.")
    md += ["", "## Recommended Next", ""]
    for step in data["recommended_next"]:
        md.append(f"- {step}")
    md.append("")

    OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print("[WRITE] PI_IMPORT_TIME_SIDE_EFFECT_AUDIT.md")
    print("[WRITE] pi_import_time_side_effect_audit.json")
    for k, v in summary.items():
        print(f"[SUMMARY] {k}={v}")
    print("[DONE] Pi import-time side-effect audit complete")
    return 0 if not compile_failures and not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())