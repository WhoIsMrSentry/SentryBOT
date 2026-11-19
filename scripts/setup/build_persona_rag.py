"""Pre-fetch persona URLs, build local SQLite+FTS5 RAG indices, and push derived Ollama models.

Every persona is built as its own Ollama model (`FROM nemotron-3.5-bolt:e4b`, e.g. `sentry:latest`,
`glados:latest`) on the configured remote Ollama PC (`http://whoismrsentry.local:11434`), while its
`urls.txt` Wiki/Web sources are preprocessed into `knowledge/*.md` and `persona_rag.sqlite3`.

Usage:
    python scripts/setup/build_persona_rag.py --persona glados --fetch --create-models
    python scripts/setup/build_persona_rag.py --all --create-models
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.ai_provider.services.persona_rag import PersonaManager  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SentryBOT Persona RAG databases and derived Ollama models.")
    parser.add_argument("--persona", default="", help="Single persona name to ingest (e.g. glados, sentry)")
    parser.add_argument("--all", action="store_true", help="Process all personas under personalities dir")
    parser.add_argument("--fetch", action="store_true", help="Fetch HTTP/HTTPS URLs from urls.txt into knowledge/")
    parser.add_argument("--force", action="store_true", help="Re-fetch cached URL pages even if already present")
    parser.add_argument("--clear-missing", action="store_true", help="Remove stale chunks missing from knowledge/")
    parser.add_argument("--create-models", action="store_true", help="Push persona Modelfiles (FROM nemotron-3.5-bolt:e4b) to remote Ollama PC")
    parser.add_argument("--ollama-url", default="", help="Override Ollama base URL (defaults to config/agent.yaml)")
    parser.add_argument("--base-dir", default="modules/ai_provider/config/personalities", help="Personalities root")
    args = parser.parse_args(argv)

    mgr = PersonaManager(args.base_dir)
    try:
        if args.persona:
            targets = [args.persona]
        else:
            targets = [item["id"] for item in mgr.list_personas()]

        results = []
        for name in targets:
            rag = mgr.get_rag(name)
            res = rag.ingest(
                fetch_urls=bool(args.fetch or args.force),
                force_fetch=bool(args.force),
                clear_missing=bool(args.clear_missing),
            )
            if args.create_models:
                res["ollama_create"] = mgr.ensure_ollama_model(name, base_url=args.ollama_url)
            results.append(res)
        print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
        return 0
    finally:
        mgr.close()


if __name__ == "__main__":
    raise SystemExit(main())
