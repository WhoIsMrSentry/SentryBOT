#!/usr/bin/env python3
"""
Generate edges.json for graph-explorer by scanning `modules/` for cross-module
imports and hints.

Writes tools/graph-explorer/edges.json
"""
import os
import re
import json
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MODULES_DIR = os.path.join(ROOT, 'modules')
OUT = os.path.join(os.path.dirname(__file__), 'edges.json')

MODULE_RE = re.compile(r"modules\.([a-z0-9_]+)")

# Heuristic type mapping for known targets
TYPE_MAP = {
    'arduino_serial': 'serial',
    'neopixel': 'http',
    'ollama': 'llm',
    'vision_bridge': 'serial',
    'speech': 'event',
    'interactions': 'event',
    'wiki_rag': 'http',
    'autonomy': 'http',
    'speak': 'http',
}


def discover_edges():
    edges = set()
    if not os.path.isdir(MODULES_DIR):
        print('modules directory not found:', MODULES_DIR)
        return []

    for root, dirs, files in os.walk(MODULES_DIR):
        for fn in files:
            if not fn.endswith('.py'):
                continue
            path = os.path.join(root, fn)
            # module name is first component under modules/
            rel = os.path.relpath(path, MODULES_DIR)
            parts = rel.split(os.sep)
            if len(parts) == 0:
                continue
            src_mod = parts[0]
            try:
                txt = open(path, 'r', encoding='utf-8').read()
            except Exception:
                continue
            for m in MODULE_RE.findall(txt):
                tgt = m
                if tgt == src_mod:
                    continue
                typ = TYPE_MAP.get(tgt, 'http')
                edges.add((src_mod, tgt, typ))
    # Also include some gateway/service-level heuristics
    # e.g., run_robot -> gw_service, gateway -> modules
    edges_list = [ {'source': s, 'target': t, 'type': typ} for (s,t,typ) in sorted(edges) ]
    return edges_list


def main():
    edges = discover_edges()
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(edges, f, indent=2, ensure_ascii=False)
    print('Wrote', OUT, 'with', len(edges), 'edges')


if __name__ == '__main__':
    main()
