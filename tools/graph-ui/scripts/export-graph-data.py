#!/usr/bin/env python3
"""Export the codebase-memory MCP graph as static JSON for the graph-ui.

Reads .codebase-memory/graph.db.zst and computes the exact same 3D layout
the MCP's live UI server produces (see codebase-memory-mcp `src/ui/layout3d.c`):
ring seed by directory cluster -> z from call-depth BFS -> anchor-preserving
Barnes-Hut local optimization. This keeps the GitHub Pages deploy visually
identical to the local `localhost:9749` view instead of drifting via an
unrelated ad-hoc layout.
"""

import subprocess, sqlite3, json, math, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DB_ZST = os.path.join(PROJECT_ROOT, ".codebase-memory", "graph.db.zst")
OUTPUT = os.path.join(HERE, "..", "public", "data.json")

# Ring/BFS/local-optimization constants — mirror layout3d.c exactly.
BH_THETA = 1.2
OCTREE_MAX_DEPTH = 26
OCTREE_MIN_HALF = 1e-4
LOCAL_REPULSION = 8.0
LOCAL_ATTRACTION = 1.0
LOCAL_ANCHOR_K = 0.25
LOCAL_ITERATIONS = 40
Z_DEPTH_SPACING = 50.0
RING_BASE_RADIUS = 500.0
RING_RADIUS_SPREAD = 250.0
RING_JITTER = 40.0
ENTRY_LABELS = {"Route", "File", "Module", "Package"}

U32_MASK = 0xFFFFFFFF


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
        "SELECT id, label, name, qualified_name, file_path FROM nodes")]
    edges = [dict(r) for r in conn.execute(
        "SELECT source_id, target_id, type FROM edges")]
    project = conn.execute("SELECT name FROM projects").fetchone()
    raw = project["name"] if project else "project"
    conn.close()
    return nodes, edges, pretty_name(raw)


# ── Hashing / deterministic jitter (mirrors layout3d.c bit-for-bit) ─────

def fnv1a(s: str) -> int:
    h = 2166136261
    for b in (s or "").encode("utf-8", errors="replace"):
        h ^= b
        h = (h * 16777619) & U32_MASK
    return h


def rand_float(seed_box):
    seed_box[0] = (seed_box[0] * 1103515245 + 12345) & U32_MASK
    return ((seed_box[0] >> 16) & 0x7FFF) / 32768.0 - 0.5


def cluster_key(file_path: str) -> str:
    """First 3 path components, matching layout3d.c's char-walk truncation."""
    return "/".join((file_path or "").split("/")[:3])[:255]


# ── Node colors/sizes (mirrors layout3d.c stellar_color / size_for_label) ──

def stellar_color(degree: int) -> str:
    if degree <= 1:
        rgb = 0xff6050
    elif degree <= 3:
        rgb = 0xff8855
    elif degree <= 5:
        rgb = 0xffa060
    elif degree <= 8:
        rgb = 0xffc070
    elif degree <= 12:
        rgb = 0xffe080
    elif degree <= 18:
        rgb = 0xfff0c0
    elif degree <= 25:
        rgb = 0xfff8e8
    elif degree <= 35:
        rgb = 0xe8e8ff
    elif degree <= 50:
        rgb = 0xc0d0ff
    else:
        rgb = 0x80a0ff
    return f"#{rgb:06x}"


_LABEL_BASE_SIZE = {
    "Project": 20.0, "Package": 15.0, "Module": 15.0, "Folder": 12.0,
    "File": 8.0, "Class": 6.0, "Struct": 6.0, "Interface": 6.0,
    "Function": 4.0, "Method": 4.0,
}


def size_for_label(label: str) -> float:
    return _LABEL_BASE_SIZE.get(label, 4.0)


# ── Barnes-Hut octree ────────────────────────────────────────────────────

class OctreeNode:
    __slots__ = ("ox", "oy", "oz", "half_size", "cx", "cy", "cz",
                 "total_mass", "body_index", "body_mass", "children")

    def __init__(self, ox, oy, oz, half):
        self.ox, self.oy, self.oz, self.half_size = ox, oy, oz, half
        self.cx = self.cy = self.cz = 0.0
        self.total_mass = 0.0
        self.body_index = -1
        self.body_mass = 0.0
        self.children = [None] * 8


def _octant(n, x, y, z):
    return (1 if x >= n.ox else 0) | (2 if y >= n.oy else 0) | (4 if z >= n.oz else 0)


def _child_center(n, o):
    q = n.half_size * 0.5
    return (n.ox + (q if o & 1 else -q),
            n.oy + (q if o & 2 else -q),
            n.oz + (q if o & 4 else -q))


def _octree_insert(n, idx, x, y, z, mass, depth):
    if n.total_mass == 0.0 and n.body_index == -1:
        n.body_index, n.body_mass = idx, mass
        n.cx, n.cy, n.cz, n.total_mass = x, y, z, mass
        return
    if depth >= OCTREE_MAX_DEPTH or n.half_size < OCTREE_MIN_HALF:
        nm = n.total_mass + mass
        n.cx = (n.cx * n.total_mass + x * mass) / nm
        n.cy = (n.cy * n.total_mass + y * mass) / nm
        n.cz = (n.cz * n.total_mass + z * mass) / nm
        n.total_mass = nm
        n.body_index = -1
        return
    if n.body_index >= 0:
        oi, ox_, oy_, oz_, om = n.body_index, n.cx, n.cy, n.cz, n.body_mass
        n.body_index = -1
        o = _octant(n, ox_, oy_, oz_)
        if n.children[o] is None:
            a, b, c = _child_center(n, o)
            n.children[o] = OctreeNode(a, b, c, n.half_size * 0.5)
        _octree_insert(n.children[o], oi, ox_, oy_, oz_, om, depth + 1)
    nm = n.total_mass + mass
    n.cx = (n.cx * n.total_mass + x * mass) / nm
    n.cy = (n.cy * n.total_mass + y * mass) / nm
    n.cz = (n.cz * n.total_mass + z * mass) / nm
    n.total_mass = nm
    o = _octant(n, x, y, z)
    if n.children[o] is None:
        a, b, c = _child_center(n, o)
        n.children[o] = OctreeNode(a, b, c, n.half_size * 0.5)
    _octree_insert(n.children[o], idx, x, y, z, mass, depth + 1)


def _octree_repulse(root, px, py, pz, mm, si, kr):
    fx = fy = fz = 0.0
    stack = [root]
    while stack:
        n = stack.pop()
        if n is None or n.total_mass == 0.0 or n.body_index == si:
            continue
        dx, dy, dz = px - n.cx, py - n.cy, pz - n.cz
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if n.body_index >= 0 or (n.half_size * 2.0 / (d + 0.001)) < BH_THETA:
            if d < 0.01:
                d = 0.01
            f = kr * mm * n.total_mass / d
            fx += f * dx / d
            fy += f * dy / d
            fz += f * dz / d
        else:
            stack.extend(c for c in n.children if c is not None)
    return fx, fy, fz


def local_optimize(xs, ys, zs, ax, ay, az, mass, es, ed):
    n = len(xs)
    for it in range(LOCAL_ITERATIONS):
        fx = [0.0] * n
        fy = [0.0] * n
        fz = [0.0] * n

        mnx, mny, mnz = min(xs), min(ys), min(zs)
        mxx, mxy, mxz = max(xs), max(ys), max(zs)
        half = max(mxx - mnx, mxy - mny, mxz - mnz) * 0.5 + 1.0
        root = OctreeNode((mnx + mxx) * 0.5, (mny + mxy) * 0.5, (mnz + mxz) * 0.5, half)
        for i in range(n):
            _octree_insert(root, i, xs[i], ys[i], zs[i], mass[i], 0)

        for i in range(n):
            rx, ry, rz = _octree_repulse(root, xs[i], ys[i], zs[i], mass[i], i, LOCAL_REPULSION)
            fx[i] += rx
            fy[i] += ry
            fz[i] += rz

        for s, t in zip(es, ed):
            dx, dy, dz = xs[t] - xs[s], ys[t] - ys[s], zs[t] - zs[s]
            fx[s] += dx * LOCAL_ATTRACTION
            fy[s] += dy * LOCAL_ATTRACTION
            fz[s] += dz * LOCAL_ATTRACTION
            fx[t] -= dx * LOCAL_ATTRACTION
            fy[t] -= dy * LOCAL_ATTRACTION
            fz[t] -= dz * LOCAL_ATTRACTION

        for i in range(n):
            fx[i] += (ax[i] - xs[i]) * LOCAL_ANCHOR_K * mass[i]
            fy[i] += (ay[i] - ys[i]) * LOCAL_ANCHOR_K * mass[i]
            fz[i] += (az[i] - zs[i]) * LOCAL_ANCHOR_K * mass[i]

        for i in range(n):
            fm = math.sqrt(fx[i] * fx[i] + fy[i] * fy[i] + fz[i] * fz[i])
            speed = 8.0 / (fm + 0.001) if fm > 8.0 else 1.0
            xs[i] += fx[i] * speed
            ys[i] += fy[i] * speed
            zs[i] += fz[i] * speed

        print(f"  local_optimize iteration {it + 1}/{LOCAL_ITERATIONS}")


# ── Call depth via BFS (all edge types, mirrors compute_call_depth) ────

def compute_call_depth(n, es, ed, labels):
    depth = [-1] * n
    queue = [i for i in range(n) if labels[i] in ENTRY_LABELS]
    if not queue:
        in_deg = [0] * n
        for t in ed:
            in_deg[t] += 1
        queue = [i for i in range(n) if in_deg[i] == 0]
    for i in queue:
        depth[i] = 0

    adj = [[] for _ in range(n)]
    for s, t in zip(es, ed):
        adj[s].append(t)

    head = 0
    while head < len(queue):
        c = queue[head]
        head += 1
        cd = depth[c]
        for t in adj[c]:
            if depth[t] == -1:
                depth[t] = cd + 1
                queue.append(t)

    for i in range(n):
        if depth[i] == -1:
            depth[i] = 0
    return depth


def compute_layout(nodes, edges):
    n = len(nodes)
    print(f"Computing layout for {n} nodes, {len(edges)} edges...")

    node_ids = [nd["id"] for nd in nodes]
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    labels = [nd["label"] for nd in nodes]

    es, ed = [], []
    deg = [0] * n
    for e in edges:
        s, t = id_to_idx.get(e["source_id"]), id_to_idx.get(e["target_id"])
        if s is None or t is None:
            continue
        es.append(s)
        ed.append(t)
        deg[s] += 1
        deg[t] += 1

    depth = compute_call_depth(n, es, ed, labels)

    xs, ys, zs = [0.0] * n, [0.0] * n, [0.0] * n
    for i, nd in enumerate(nodes):
        ck = cluster_key(nd["file_path"])
        h = fnv1a(ck)
        angle = (h & 0xFFFF) / 65535.0 * 6.2832
        radius = RING_BASE_RADIUS + (((h >> 16) & 0xFF) / 255.0) * RING_RADIUS_SPREAD

        seed_box = [fnv1a(nd["qualified_name"] or nd["name"] or "")]
        jitter_x = rand_float(seed_box) * RING_JITTER
        jitter_y = rand_float(seed_box) * RING_JITTER

        xs[i] = radius * math.cos(angle) + jitter_x
        ys[i] = radius * math.sin(angle) + jitter_y
        zs[i] = -depth[i] * Z_DEPTH_SPACING

    anchor_x, anchor_y, anchor_z = list(xs), list(ys), list(zs)
    mass = [d + 1.0 for d in deg]

    local_optimize(xs, ys, zs, anchor_x, anchor_y, anchor_z, mass, es, ed)

    pos = {node_ids[i]: [xs[i], ys[i], zs[i]] for i in range(n)}
    return pos, id_to_idx, deg


def write_output(nodes, edges, pos, id_to_idx, deg, project_name):
    graph_nodes = []
    for nd in nodes:
        nid = nd["id"]
        if nid not in id_to_idx:
            continue
        idx = id_to_idx[nid]
        p = pos[nid]
        d = deg[idx]
        deg_boost = min(d * 0.3, 10.0) if d > 5 else 0.0
        graph_nodes.append({
            "id": idx,
            "name": nd["name"] if nd["name"] else "?",
            "label": nd["label"],
            "file_path": nd["file_path"] or "",
            "x": round(p[0], 4),
            "y": round(p[1], 4),
            "z": round(p[2], 4),
            "size": round(size_for_label(nd["label"]) + deg_boost, 3),
            "color": stellar_color(d),
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
    print("=== graph-ui data exporter (layout3d.c-compatible) ===")
    db_path = decompress_db()
    try:
        nodes, edges, project = read_graph(db_path)
        print(f"Project: {project}, nodes: {len(nodes)}, edges: {len(edges)}")
        pos, id_to_idx, deg = compute_layout(nodes, edges)
        write_output(nodes, edges, pos, id_to_idx, deg, project)
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    main()
