"""Shared filesystem, parsing, formatting, and output helpers for SentryBOT audit tools."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Iterable

EXCLUDE_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".sentrybot_state",
    "node_modules",
    "dist",
    "build",
    "reports",
}

DEFAULT_AUDIT_SUFFIXES = {
    ".py",
    ".json",
    ".yml",
    ".yaml",
    ".md",
    ".ps1",
    ".toml",
    ".ini",
    ".service",
    ".sh",
}

VOICE_CONFIG_FILES = [
    "modules/voice/speak/config/config.yml",
    "modules/voice/speech/config/config.yml",
    "modules/voice/wakeword/config/config.yml",
]


def repo_root() -> Path:
    """Return the repository root directory and ensure it is on `sys.path`."""
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def resolve_output_paths(
    root: Path,
    output_dir: str | Path | None,
    md_filename: str,
    json_filename: str,
) -> tuple[Path, Path]:
    """Resolve and create `(md_path, json_path)` inside `--output-dir` or `<root>/reports`."""
    target_dir = Path(output_dir).resolve() if output_dir else (root / "reports")
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / md_filename, target_dir / json_filename


def parse_output_dir_arg(
    argv: list[str] | None = None,
    *,
    description: str = "SentryBOT audit tool",
) -> Path | None:
    """Parse standard `--output-dir` flag shared by report-only audit scripts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory where JSON/Markdown reports are written (default: <repo_root>/reports).",
    )
    args = parser.parse_args(argv)
    return Path(args.output_dir) if args.output_dir else None


def should_skip(path: Path, exclude_parts: Iterable[str] = EXCLUDE_PARTS) -> bool:
    excluded = set(exclude_parts)
    return any(part in excluded for part in path.parts)


def rel(path: Path, root: Path | None = None) -> str:
    base = root or repo_root()
    return str(path.relative_to(base)).replace("\\", "/")


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


def summarize(value: Any, *, depth: int = 0, list_sample: int = 8) -> Any:
    """Produce a compact structural summary of parsed JSON/YAML config data."""
    if depth > 2:
        return "..."
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:60]:
            if isinstance(item, dict):
                out[str(key)] = {"type": "object", "keys": list(item.keys())[:24], "count": len(item)}
            elif isinstance(item, list):
                out[str(key)] = {"type": "list", "count": len(item)}
            else:
                out[str(key)] = item
        return out
    if isinstance(value, list):
        return {"type": "list", "count": len(value), "sample": value[:list_sample]}
    return value


def iter_repo_files(
    root: Path,
    scan_roots: Iterable[str],
    *,
    suffixes: Iterable[str] = DEFAULT_AUDIT_SUFFIXES,
    exclude_parts: Iterable[str] = EXCLUDE_PARTS,
) -> list[Path]:
    """Enumerate repository files matching `suffixes` while skipping excluded directories."""
    suffix_set = {s.lower() for s in suffixes}
    out: list[Path] = []
    for root_name in scan_roots:
        scan_dir = root / root_name
        if scan_dir.exists():
            out.extend(
                p
                for p in scan_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in suffix_set and not should_skip(p, exclude_parts)
            )
    return sorted(set(out))


def ast_symbol_context(path: Path) -> dict[int, str]:
    """Map line numbers in a Python source file to enclosing `ClassDef` / `FunctionDef` names."""
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
                for line_no in range(start, end + 1):
                    contexts[line_no] = f"{type(node).__name__}:{node.name}"
    return contexts


def line_snippets(lines: list[str], hit_line: int, radius: int = 2) -> str:
    start = max(1, hit_line - radius)
    end = min(len(lines), hit_line + radius)
    return "\n".join(f"{n:04d}: {lines[n - 1]}" for n in range(start, end + 1))


def table(headers: list[str], rows: list[list[Any]], max_cell_len: int = 900) -> str:
    """Format a GitHub-flavored Markdown table with bounded cell lengths."""
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("\n", "<br>")[:max_cell_len] for x in row) + " |")
    return "\n".join(out)


def write_audit_reports(
    out_md: Path,
    out_json: Path,
    md_content: str | list[str],
    data: dict[str, Any],
) -> None:
    """Persist audit JSON and Markdown outputs using UTF-8 encoding."""
    md_text = "\n".join(md_content) if isinstance(md_content, list) else md_content
    out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    out_md.write_text(md_text, encoding="utf-8")
