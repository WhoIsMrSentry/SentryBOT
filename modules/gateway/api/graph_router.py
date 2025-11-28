from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query


def _repo_root() -> Path:
    # modules/gateway/api/ -> modules/gateway -> modules -> <repo_root>
    return Path(__file__).resolve().parents[3]


def _safe_join(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if root not in p.parents and p != root:
        raise HTTPException(400, detail="Path outside repository")
    return p


def _collect_tree(base: Path, max_files_per_dir: int = 500) -> Dict[str, Any]:
    def list_dir(p: Path) -> Dict[str, Any]:
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except Exception:
            entries = []
        children: List[Dict[str, Any]] = []
        count = 0
        for e in entries:
            if count >= max_files_per_dir:
                children.append({"name": "… (trimmed)", "type": "info"})
                break
            if e.name.startswith(".__") or e.name == "__pycache__":
                continue
            if e.is_dir():
                children.append({
                    "name": e.name,
                    "path": str(e.relative_to(base)),
                    "type": "dir",
                    "children": list_dir(e),
                })
            else:
                children.append({
                    "name": e.name,
                    "path": str(e.relative_to(base)),
                    "type": "file",
                    "size": e.stat().st_size if e.exists() else 0,
                })
            count += 1
        return children

    tree: Dict[str, Any] = {
        "name": base.name,
        "path": "",
        "type": "dir",
        "children": [],
    }

    # Focus on top-level and modules
    interesting = [
        "run_robot.py",
        "README.md",
        "modules",
        "platforms",
        "arduino",
    ]
    for name in interesting:
        p = base / name
        if p.exists():
            node = {
                "name": name,
                "path": str(p.relative_to(base)) if p != base else "",
                "type": "dir" if p.is_dir() else "file",
                "children": list_dir(p) if p.is_dir() else None,
            }
            tree["children"].append(node)

    return tree


def _relations() -> Dict[str, Any]:
    # Lightweight static relation hints derived from bootstrap and READMEs
    nodes = [
        {"id": "run_robot", "label": "run_robot.py", "kind": "entry"},
        {"id": "gateway", "label": "Gateway", "kind": "service"},
        {"id": "arduino", "label": "Arduino Serial", "kind": "module"},
        {"id": "neopixel", "label": "NeoPixel", "kind": "module"},
        {"id": "interactions", "label": "Interactions", "kind": "module"},
        {"id": "speech", "label": "Speech (ASR)", "kind": "module"},
        {"id": "speak", "label": "Speak (TTS)", "kind": "module"},
        {"id": "ollama", "label": "Ollama (LLM)", "kind": "module"},
        {"id": "camera", "label": "Camera", "kind": "module"},
        {"id": "vision_bridge", "label": "Vision Bridge", "kind": "module"},
        {"id": "wiki_rag", "label": "Wiki RAG", "kind": "module"},
        {"id": "animate", "label": "Animate", "kind": "module"},
        {"id": "piservo", "label": "Pi Servo", "kind": "module"},
        {"id": "hardware", "label": "Hardware", "kind": "module"},
        {"id": "telemetry", "label": "Telemetry", "kind": "module"},
        {"id": "diagnostics", "label": "Diagnostics", "kind": "module"},
        {"id": "state_manager", "label": "State Manager", "kind": "module"},
        {"id": "scheduler", "label": "Scheduler", "kind": "module"},
        {"id": "notifier", "label": "Notifier", "kind": "module"},
        {"id": "mutagen", "label": "Mutagen", "kind": "module"},
        {"id": "ota", "label": "OTA", "kind": "module"},
        {"id": "config_center", "label": "Config Center", "kind": "module"},
        {"id": "logwrapper", "label": "Logs", "kind": "module"},
    ]
    edges = [
        # Boot chain
        {"source": "run_robot", "target": "gateway", "type": "boot"},
        # Gateway mounts
        *[{"source": "gateway", "target": n["id"], "type": "mount"} for n in nodes if n["id"] not in ("run_robot", "gateway")],
        # Inter-module calls
        {"source": "interactions", "target": "neopixel", "type": "http"},
        {"source": "vision_bridge", "target": "arduino", "type": "serial"},
        {"source": "animate", "target": "arduino", "type": "serial"},
        {"source": "speech", "target": "interactions", "type": "event"},
        {"source": "speech", "target": "ollama", "type": "http"},
        {"source": "ollama", "target": "speak", "type": "http"},
        {"source": "wiki_rag", "target": "ollama", "type": "llm"},
        {"source": "diagnostics", "target": "gateway", "type": "health"},
    ]
    return {"nodes": nodes, "edges": edges}


def get_router() -> APIRouter:
    # Use a distinct prefix to avoid clashing with StaticFiles mounted at /graph
    r = APIRouter(prefix="/graph-api", tags=["graph"])

    @r.get("/tree")
    def tree():
        root = _repo_root()
        return _collect_tree(root)

    @r.get("/file")
    def file(path: str = Query(..., description="Repository-relative path"), max_kb: int = 256):
        root = _repo_root()
        p = _safe_join(root, path)
        if not p.exists() or not p.is_file():
            raise HTTPException(404, detail="File not found")
        data = p.read_bytes()
        if len(data) > max_kb * 1024:
            data = data[: max_kb * 1024]
        # try decode as text
        try:
            text = data.decode("utf-8", errors="replace")
            return {"ok": True, "path": path, "text": text}
        except Exception:
            return {"ok": True, "path": path, "base64": data.decode("latin1", errors="replace")}

    @r.get("/relations")
    def relations():
        return _relations()

    return r
