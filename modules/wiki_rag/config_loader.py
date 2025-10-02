from __future__ import annotations
import os
from typing import Any, Dict
import yaml

DEFAULT_CFG = {
    "server": {"host": "0.0.0.0", "port": 8098},
    "ollama": {"base_url": "http://localhost:11434", "model": "llama3.2:3b", "request_timeout": 60.0},
    "storage": {
        "persist_dir": "modules/wiki_rag/storage/index_storage",
        "knowledge_dir": "modules/wiki_rag/storage/knowledge",
    },
    "persona": {
        "active": "glados",
        "dir": "modules/ollama/config/personalities",
    },
    "preprocess": {
        "cut_offs": ["##  Gallery", "##  Trivia", "##  References"],
    },
    "ollama_service": {
        "base_url": "http://localhost:8099"
    },
}


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    path = config_path or os.environ.get("WIKI_RAG_CFG", "modules/wiki_rag/config/config.yml")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    cfg = DEFAULT_CFG.copy()
    for k, v in (data or {}).items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg
