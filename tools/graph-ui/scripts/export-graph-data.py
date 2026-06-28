#!/usr/bin/env python3
"""Export the codebase-memory MCP graph as static JSON for the graph-ui.
Reads .codebase-memory/graph.db.zst, computes 3D layout, writes data.json."""

import subprocess, sqlite3, json, math, random, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DB_ZST = os.path.join(PROJECT_ROOT, ".codebase-memory", "graph.db.zst")
OUTPUT = os.path.join(HERE, "..", "public", "data.json")

# Label colors (hex)
LABEL_COLORS = {
    "Module": "#e05252", "File": "#f59e0b", "Function": "#34d399",
    "Method": "#3b82f6", "Class": "#a78bfa", "Interface": "#f472b6",
    "Variable": "#14b8a6", "Route": "#8b5cf6", "Import": "#64748b",
    "Decorator": "#84cc16", "Type": "#06b6d4", "Parameter": "#737373",
    "Resource": "#d946ef",
}

# Edge type colors
EDGE_TYPE_COLORS = {
    "CALLS": "#34d399", "IMPORTS": "#f59e0b", "DEFINES": "#3b82f6",
    "IMPLEMENTS": "#a78bfa", "INHERITS": "#f472b6", "CONTAINS_FILE": "#64748b",
    "DATA_FLOWS": "#14b8a6", "HTTP_CALLS": "#ef4444", "SIMILAR_TO": "#84cc16",
    "EMITS": "#22c55e", "LISTENS_ON": "#f97316",
    "CROSS_HTTP_CALLS": "#ef4444", "CROSS_ASYNC_CALLS": "#f97316",
}


def decompress_db():
    if not os.path.exists(DB_ZST):
        print(f"ERROR: {DB_ZST} not found. Run codebase-memory-mcp index first.")
        sys.exit(1)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    subprocess.run(["zstd", "-d", "-f", DB_ZST, "-o", tmp.name],
                   check=True, capture_output=True)
    return tmp.name


def pretty_name(raw: str) -> str:
    """Convert 'home-whoismrsentry-Project-SentryBOT-V5' -> 'SentryBOT'"""
    parts = raw.replace("-", " ").split()
    for p in parts:
        if p.lower() in ("project",):
            continue
        if "sentrybot" in p.lower():
            return "SentryBOT"
    return raw

def read_graph(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    nodes = [dict(r) for r in conn.execute(
        "SELECT id, label, name, qualified_name, file_path, properties FROM nodes")]
    edges = [dict(r) for r in conn.execute(
        "SELECT source_id, target_id, type FROM edges")]
    project = conn.execute("SELECT name FROM projects").fetchone()
    raw = project["name"] if project else "project"
    conn.close()
    return nodes, edges, pretty_name(raw)


def compute_layout(nodes, edges):
    n = len(nodes)
    print(f"Computing layout for {n} nodes, {len(edges)} edges...")

    node_ids = [nd["id"] for nd in nodes]
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    # Group by label for initial cluster placement
    label_groups = {}
    for nd in nodes:
        lbl = nd["label"]
        label_groups.setdefault(lbl, []).append(nd["id"])

    # Place label groups on a sphere surface (smaller radius this time)
    labels = sorted(label_groups.keys())
    R = 8.0
    pos = {}
    for i, lbl in enumerate(labels):
        theta = 2 * math.pi * i / len(labels)
        phi = math.acos(2 * i / len(labels) - 1) if len(labels) > 1 else math.pi / 2
        center = [R * math.sin(phi) * math.cos(theta),
                  R * math.sin(phi) * math.sin(theta),
                  R * math.cos(phi)]
        group = label_groups[lbl]
        for j, nid in enumerate(group):
            offset = [random.uniform(-2, 2) for _ in range(3)]
            pos[nid] = [center[k] + offset[k] for k in range(3)]

    # Spring layout: connected nodes attract, all repel weakly
    ideal_dist = 3.0
    spring_k = 0.08
    repel_k = 0.3

    for iteration in range(60):
        # Spring forces (edges)
        for edge in edges:
            s, t = edge["source_id"], edge["target_id"]
            if s not in id_to_idx or t not in id_to_idx:
                continue
            ps, pt = pos[s], pos[t]
            dx = pt[0] - ps[0]; dy = pt[1] - ps[1]; dz = pt[2] - ps[2]
            dist = max(math.sqrt(dx*dx + dy*dy + dz*dz), 0.1)
            stretch = (dist - ideal_dist) / dist
            fx = dx * stretch * spring_k
            fy = dy * stretch * spring_k
            fz = dz * stretch * spring_k
            ps[0] += fx; ps[1] += fy; ps[2] += fz
            pt[0] -= fx; pt[1] -= fy; pt[2] -= fz

        # Weak repulsion from cluster centers (keeps labels separated)
        for i, lbl_i in enumerate(labels):
            for j, lbl_j in enumerate(labels):
                if j <= i:
                    continue
                ci = [R * math.sin(2 * math.pi * i / len(labels)),
                      R * math.cos(2 * math.pi * i / len(labels)), 0]
                cj = [R * math.sin(2 * math.pi * j / len(labels)),
                      R * math.cos(2 * math.pi * j / len(labels)), 0]
                dx = ci[0] - cj[0]; dy = ci[1] - cj[1]; dz = ci[2] - cj[2]
                dist = max(math.sqrt(dx*dx + dy*dy + dz*dz), 0.1)
                # Only apply if clusters are too close
                if dist < ideal_dist * 2:
                    push = (ideal_dist * 2 - dist) / dist * repel_k * 0.5
                    for nid in label_groups[lbl_i]:
                        pos[nid][0] -= dx * push
                        pos[nid][1] -= dy * push
                        pos[nid][2] -= dz * push
                    for nid in label_groups[lbl_j]:
                        pos[nid][0] += dx * push
                        pos[nid][1] += dy * push
                        pos[nid][2] += dz * push

        if iteration % 20 == 0:
            print(f"  Spring iteration {iteration+1}/60")

    # Normalize to [0, 20]
    xs = [pos[nid][0] for nid in node_ids]
    ys = [pos[nid][1] for nid in node_ids]
    zs = [pos[nid][2] for nid in node_ids]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    scl = min(20 / (max_x - min_x) if max_x > min_x else 1,
              20 / (max_y - min_y) if max_y > min_y else 1,
              20 / (max_z - min_z) if max_z > min_z else 1)
    cx, cy, cz = (min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2
    for nid in node_ids:
        pos[nid][0] = (pos[nid][0] - cx) * scl + 10
        pos[nid][1] = (pos[nid][1] - cy) * scl + 10
        pos[nid][2] = (pos[nid][2] - cz) * scl + 10

    return pos, id_to_idx


def write_output(nodes, edges, pos, id_to_idx, project_name):
    # Build degree map
    degree = {}
    for nid in pos:
        degree[nid] = 0
    for e in edges:
        s, t = e["source_id"], e["target_id"]
        if s in id_to_idx:
            degree[s] = degree.get(s, 0) + 1
        if t in id_to_idx:
            degree[t] = degree.get(t, 0) + 1

    # Map label to colors
    random.seed(42)
    label_color_map = {}
    for nd in nodes:
        lbl = nd["label"]
        if lbl not in label_color_map:
            if lbl in LABEL_COLORS:
                label_color_map[lbl] = LABEL_COLORS[lbl]
            else:
                label_color_map[lbl] = "#{:02x}{:02x}{:02x}".format(
                    random.randint(100, 220), random.randint(100, 220),
                    random.randint(100, 220))

    graph_nodes = []
    for nd in nodes:
        nid = nd["id"]
        if nid not in id_to_idx:
            continue
        p = pos[nid]
        graph_nodes.append({
            "id": id_to_idx[nid],
            "name": nd["name"] if nd["name"] else "?",
            "label": nd["label"],
            "file_path": nd["file_path"] or "",
            "x": round(p[0], 4),
            "y": round(p[1], 4),
            "z": round(p[2], 4),
            "size": max(0.5, min(5, math.log2(degree.get(nid, 0) + 1) * 0.8)),
            "color": label_color_map[nd["label"]],
        })

    graph_edges = [{
        "source": id_to_idx[e["source_id"]],
        "target": id_to_idx[e["target_id"]],
        "type": e["type"],
    } for e in edges if e["source_id"] in id_to_idx and e["target_id"] in id_to_idx]

    data = {
        "nodes": graph_nodes,
        "edges": graph_edges,
        "total_nodes": len(graph_nodes),
        "project": project_name,
        "indexed_at": "",
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(data, f, indent=1)
    print(f"Wrote {len(graph_nodes)} nodes, {len(graph_edges)} edges to {OUTPUT}")
    print(f"File size: {os.path.getsize(OUTPUT) / 1024 / 1024:.1f} MB")


def main():
    print("=== graph-ui data exporter ===")
    db_path = decompress_db()
    try:
        nodes, edges, project = read_graph(db_path)
        print(f"Project: {project}, nodes: {len(nodes)}, edges: {len(edges)}")
        pos, id_to_idx = compute_layout(nodes, edges)
        write_output(nodes, edges, pos, id_to_idx, project)
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    main()
