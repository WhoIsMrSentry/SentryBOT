from __future__ import annotations

import ast
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._audit_common import (  # noqa: E402
    ast_symbol_context,
    iter_repo_files,
    line_snippets as snippets,
    parse_output_dir_arg,
    read_text,
    rel as _common_rel,
    resolve_output_paths,
    table,
    write_audit_reports,
)

MD_NAME = "PI_RUNTIME_STUB_LEGACY_CALLER_AUDIT.md"
JSON_NAME = "pi_runtime_stub_legacy_caller_audit.json"

SCAN_ROOTS = ["modules", "apps", "services", "config"]

TERMS = [
    "stub",
    "dummy",
    "fake",
    "mock",
    "legacy",
    "deprecated",
    "fallback",
    "placeholder",
    "no-op",
    "noop",
]

RUNTIME_CRITICAL_HINTS = [
    "camera",
    "capture",
    "vlm",
    "vision",
    "speech",
    "speak",
    "wakeword",
    "audio",
    "gateway",
    "autonomy",
    "brain",
    "hardware",
    "arduino",
    "esp",
    "neopixel",
    "oled",
    "piservo",
    "expression",
]

KNOWN_REVIEW_FILES = [
    "modules/visual_output/oled_faces/services/legacy_map.py",
]


def rel(path: Path) -> str:
    return _common_rel(path, ROOT)


def iter_files() -> list[Path]:
    return iter_repo_files(ROOT, SCAN_ROOTS)


def iter_py_runtime_files() -> list[Path]:
    return [p for p in iter_files() if p.suffix.lower() == ".py"]


def module_name_for_path(path_s: str) -> str | None:
    if not path_s.endswith(".py"):
        return None
    return path_s[:-3].replace("/", ".")


def symbol_name_for_path(path_s: str) -> str:
    return Path(path_s).stem


def line_kind(line: str) -> str:
    stripped = line.strip()
    triple_double = chr(34) * 3
    triple_single = chr(39) * 3
    if not stripped:
        return "blank"
    if stripped.startswith("#"):
        return "comment"
    if stripped.startswith((triple_double, triple_single)) or stripped.endswith((triple_double, triple_single)):
        return "docstring_edge"
    return "code_or_text"


def classify(path_s: str, term: str, line: str, kind: str, context: str) -> str:
    lower = f"{path_s} {line} {context}".lower()

    if path_s.endswith((".md", ".txt")):
        return "documentation"
    if path_s.startswith("config/"):
        return "config_review"

    if term == "fallback":
        if path_s in {"modules/camera/api/router.py", "modules/gateway/services/bootstrap.py", "modules/runtime_console/tui_v2.py"}:
            return "expected_degraded_path"
        if any(x in lower for x in ["safe fallback", "fallback to", "fallback when", "fallback if", "degraded", "optional"]):
            return "expected_degraded_path"
        return "review"

    if term == "mock":
        if "test" in lower or "unittest" in lower:
            return "dev_only"
        return "review"

    if term in {"stub", "dummy", "fake", "placeholder", "noop", "no-op"}:
        if path_s == "modules/runtime_console/tui_v2.py":
            return "expected_test_or_preview"
        if path_s == "modules/autonomy/services/companion_goal_executor.py" and term in {"noop", "no-op"}:
            return "expected_degraded_path"
        if path_s in {"modules/interactions/services/adapters/neopixel_client.py", "modules/hardware/neopixel/services/driver.py"}:
            return "expected_degraded_path"
        if path_s == "modules/voice/speak/services/tts.py" and term in {"dummy", "placeholder"}:
            return "expected_test_or_preview"
        if any(x in lower for x in ["test", "example", "simulation", "dry_run", "dry-run", "preview", "test-tone", "safe degraded", "safe semantic"]):
            return "expected_test_or_preview"
        return "runtime_replacement_candidate"

    if term in {"legacy", "deprecated"}:
        if path_s in {"modules/autonomy/services/brain_parts/responses.py", "modules/camera/api/router.py", "modules/gateway/services/bootstrap.py"}:
            return "compatibility_review"
        if path_s == "modules/voice/speak/config_loader.py":
            return "compatibility_review"
        if path_s.startswith("modules/visual_output/oled_faces/"):
            return "compatibility_review"
        if path_s in {"modules/vlm_bridge/services/llm_client.py", "modules/vlm_bridge/services/people_memory.py", "modules/vlm_bridge/services/person_identity.py", "modules/vlm_bridge/services/processor.py"}:
            return "compatibility_review"
        if any(x in lower for x in ["compat", "compatibility", "alias", "adapter", "migration", "kept"]):
            return "compatibility_review"
        return "runtime_replacement_candidate"

    return "review"


def file_record(path: Path) -> dict[str, Any] | None:
    path_s = rel(path)
    text = read_text(path)
    lines = text.splitlines()
    low_path = path_s.lower()
    ctx = ast_symbol_context(path)
    hits = []

    for term in TERMS:
        if term in low_path:
            hits.append({
                "line": 0,
                "term": term,
                "severity": classify(path_s, term, path_s, "filename", ""),
                "kind": "filename",
                "context": "",
                "text": path_s,
                "snippet": path_s,
            })

    for idx, line in enumerate(lines, start=1):
        low_line = line.lower()
        for term in TERMS:
            if term not in low_line:
                continue
            kind = line_kind(line)
            context = ctx.get(idx, "")
            severity = classify(path_s, term, line, kind, context)
            hits.append({
                "line": idx,
                "term": term,
                "severity": severity,
                "kind": kind,
                "context": context,
                "text": line.strip()[:500],
                "snippet": snippets(lines, idx),
            })

    if not hits:
        return None

    severities = Counter(h["severity"] for h in hits)
    terms = sorted({h["term"] for h in hits})
    return {
        "path": path_s,
        "module": module_name_for_path(path_s),
        "symbol": symbol_name_for_path(path_s),
        "suffix": path.suffix.lower(),
        "runtime_critical_hint": any(x in path_s.lower() for x in RUNTIME_CRITICAL_HINTS),
        "known_review_file": path_s in KNOWN_REVIEW_FILES,
        "lines": len(lines),
        "hit_count": len(hits),
        "terms": terms,
        "severities": dict(severities),
        "hits": hits,
    }


def import_edges() -> list[dict[str, Any]]:
    edges = []
    for path in iter_py_runtime_files():
        path_s = rel(path)
        try:
            tree = ast.parse(read_text(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append({
                        "from_path": path_s,
                        "from_module": module_name_for_path(path_s),
                        "import_module": alias.name,
                        "import_name": "",
                        "line": node.lineno,
                    })
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                for alias in node.names:
                    edges.append({
                        "from_path": path_s,
                        "from_module": module_name_for_path(path_s),
                        "import_module": base,
                        "import_name": alias.name,
                        "line": node.lineno,
                    })
    return edges


def text_references(targets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    refs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    target_keys = []
    for rec in targets:
        keys = {rec["path"]}
        if rec.get("module"):
            keys.add(rec["module"])
        if rec.get("symbol"):
            keys.add(rec["symbol"])
        for key in keys:
            if key:
                target_keys.append((rec["path"], key))
    for path in iter_files():
        path_s = rel(path)
        text = read_text(path)
        for target_path, key in target_keys:
            if target_path == path_s:
                continue
            if key and key in text:
                lines = text.splitlines()
                hit_lines = []
                for idx, line in enumerate(lines, start=1):
                    if key in line:
                        hit_lines.append(idx)
                for line_no in hit_lines[:8]:
                    refs[target_path].append({
                        "from_path": path_s,
                        "line": line_no,
                        "key": key,
                        "snippet": snippets(lines, line_no, radius=1),
                    })
    return refs


def direct_import_callers(records: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        module = rec.get("module")
        symbol = rec.get("symbol")
        if not module:
            continue
        for edge in edges:
            imported_full = edge["import_module"]
            if edge["import_name"]:
                imported_full = f"{edge['import_module']}.{edge['import_name']}"
            if (
                edge["import_module"] == module
                or imported_full == module
                or edge["import_module"].startswith(module + ".")
                or (symbol and edge["import_name"] == symbol)
            ):
                out[rec["path"]].append(edge)
    return out


def main(argv: list[str] | None = None) -> int:
    output_dir = parse_output_dir_arg(argv, description="Pi runtime stub/legacy caller audit")
    out_md, out_json = resolve_output_paths(ROOT, output_dir, MD_NAME, JSON_NAME)

    files = iter_files()
    records = [r for p in files if (r := file_record(p))]
    edges = import_edges()
    callers = direct_import_callers(records, edges)
    refs = text_references(records)

    for rec in records:
        rec["direct_import_callers"] = callers.get(rec["path"], [])
        rec["text_references"] = refs.get(rec["path"], [])[:30]
        rec["caller_count"] = len(rec["direct_import_callers"]) + len(rec["text_references"])

    replacement_candidates = [
        r for r in records
        if r["suffix"] == ".py"
        and r["runtime_critical_hint"]
        and r["severities"].get("runtime_replacement_candidate", 0) > 0
    ]
    compatibility_reviews = [
        r for r in records
        if r["suffix"] == ".py"
        and (
            r["severities"].get("compatibility_review", 0) > 0
            or r["severities"].get("expected_degraded_path", 0) > 0
        )
    ]
    docs = [r for r in records if r["severities"].get("documentation", 0) > 0]
    configs = [r for r in records if r["severities"].get("config_review", 0) > 0]

    severity_counts = Counter()
    term_counts = Counter()
    for rec in records:
        severity_counts.update(rec["severities"])
        term_counts.update(rec["terms"])

    summary = {
        "target": "Pi/Linux robot runtime",
        "pc_is_dev_host_only": True,
        "files_scanned": len(files),
        "records_with_terms": len(records),
        "runtime_replacement_candidate_files": len(replacement_candidates),
        "compatibility_review_files": len(compatibility_reviews),
        "documentation_files": len(docs),
        "config_review_files": len(configs),
        "severity_counts": dict(severity_counts),
        "term_counts": dict(term_counts),
    }

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_type": "pi_runtime_stub_legacy_caller_audit",
        "summary": summary,
        "replacement_candidates": replacement_candidates,
        "compatibility_reviews": compatibility_reviews,
        "documentation_records": docs,
        "config_records": configs,
        "all_records": records,
        "recommended_next": [
            "Do not delete stub/legacy files without caller analysis.",
            "If a candidate has callers, replace through an adapter or update callers first.",
            "If a candidate has zero callers and no dynamic gateway usage, mark for cleanup after CI guard.",
            "Keep degraded/fallback paths when they represent safe robot behavior with missing optional hardware.",
            "Next patch should target only one confirmed candidate at a time.",
        ],
    }

    md = [
        "# SentryBOT Pi Runtime Stub/Legacy Caller Audit",
        "",
        f"Generated: `{data['generated_at']}`",
        "",
        "Target: Pi/Linux robot runtime. PC remains only the development/test host.",
        "",
        "Report-only. No code changed and no hardware/camera/VLM/motion was started.",
        "",
        "Purpose: identify stub/dummy/fake/legacy/deprecated/fallback surfaces and their callers before cleanup.",
        "",
        "## Summary",
        "",
        table(["metric", "value"], [[k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v] for k, v in summary.items()]),
        "",
        "## Runtime Replacement Candidates",
        "",
    ]
    if replacement_candidates:
        md.append(table(["path", "terms", "severities", "callers", "known_review"], [
            [
                r["path"],
                ", ".join(r["terms"]),
                json.dumps(r["severities"], ensure_ascii=False),
                r["caller_count"],
                r["known_review_file"],
            ]
            for r in replacement_candidates
        ]))
        for r in replacement_candidates[:50]:
            md += ["", f"### `{r['path']}`", ""]
            md.append(table(["line", "term", "severity", "kind", "context", "text"], [
                [h["line"], h["term"], h["severity"], h["kind"], h["context"], h["text"]]
                for h in r["hits"][:16]
            ]))
            if r["direct_import_callers"]:
                md += ["", "Direct import callers:", ""]
                md.append(table(["from_path", "import_module", "import_name", "line"], [
                    [c["from_path"], c["import_module"], c["import_name"], c["line"]]
                    for c in r["direct_import_callers"][:20]
                ]))
            if r["text_references"]:
                md += ["", "Text references:", ""]
                md.append(table(["from_path", "line", "key", "snippet"], [
                    [c["from_path"], c["line"], c["key"], c["snippet"]]
                    for c in r["text_references"][:20]
                ]))
    else:
        md.append("No runtime replacement candidates found.")
    md += [
        "",
        "## Compatibility / Degraded Path Reviews",
        "",
    ]
    if compatibility_reviews:
        md.append(table(["path", "terms", "severities", "callers"], [
            [r["path"], ", ".join(r["terms"]), json.dumps(r["severities"], ensure_ascii=False), r["caller_count"]]
            for r in compatibility_reviews[:160]
        ]))
    else:
        md.append("No compatibility/degraded review files found.")
    md += [
        "",
        "## Config Records",
        "",
    ]
    if configs:
        md.append(table(["path", "terms", "severities"], [
            [r["path"], ", ".join(r["terms"]), json.dumps(r["severities"], ensure_ascii=False)]
            for r in configs[:120]
        ]))
    else:
        md.append("No config records found.")
    md += [
        "",
        "## Documentation Records",
        "",
    ]
    if docs:
        md.append(table(["path", "terms", "severities"], [
            [r["path"], ", ".join(r["terms"]), json.dumps(r["severities"], ensure_ascii=False)]
            for r in docs[:120]
        ]))
    else:
        md.append("No documentation records found.")
    md += ["", "## Recommended Next", ""]
    for step in data["recommended_next"]:
        md.append(f"- {step}")
    md.append("")

    write_audit_reports(out_md, out_json, md, data)

    print(f"[WRITE] {rel(out_md) if out_md.is_relative_to(ROOT) else out_md}")
    print(f"[WRITE] {rel(out_json) if out_json.is_relative_to(ROOT) else out_json}")
    for k, v in summary.items():
        if isinstance(v, dict):
            print(f"[SUMMARY] {k}={json.dumps(v, ensure_ascii=False)}")
        else:
            print(f"[SUMMARY] {k}={v}")
    print("[DONE] Pi runtime stub/legacy caller audit complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())