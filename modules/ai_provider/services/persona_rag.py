"""Persona manifest, Wiki/URL scraping, and SQLite+FTS5+ONNX RAG for characters.

Replaces the heavy LlamaIndex + Flask server pattern from GLaDOS_Voice with a
fast local SQLite + FTS5 + shared ONNX e5-small vector index stored inside each
persona folder (`modules/ai_provider/config/personalities/<name>/`).
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from modules.cognitive_memory.services.text_utils import _stem_tokens, _tokens
from modules.common.web_extractor import fetch_url_text

logger = logging.getLogger("ai_provider.persona_rag")

EmbedFn = Callable[[str], Any]
_DEFAULT_PERSONA_DIR = Path("modules/ai_provider/config/personalities")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def chunk_markdown(text: str, *, source: str = "", chunk_chars: int = 750, overlap_chars: int = 100) -> List[Dict[str, str]]:
    """Split Markdown or prose into clean overlapping chunks while preserving section headings."""
    raw = str(text or "").strip()
    if not raw:
        return []
    blocks = [b.strip() for b in re.split(r"\n{2,}", raw) if b.strip()]
    chunks: List[Dict[str, str]] = []
    cur_heading = ""
    buf: List[str] = []
    buf_len = 0

    def _flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        body = "\n\n".join(buf).strip()
        if body:
            chunks.append({"source": source, "title": cur_heading, "text": body})
        if overlap_chars > 0 and body:
            tail = body[-overlap_chars:].strip()
            buf = [tail] if tail else []
            buf_len = len(tail)
        else:
            buf = []
            buf_len = 0

    for block in blocks:
        if block.startswith("#"):
            first_line = block.splitlines()[0].lstrip("# ").strip()
            if buf and buf_len > chunk_chars // 2:
                _flush()
            cur_heading = first_line[:120]
        if len(block) > chunk_chars:
            if buf:
                _flush()
            start = 0
            while start < len(block):
                slice_text = block[start : start + chunk_chars].strip()
                if slice_text:
                    chunks.append({"source": source, "title": cur_heading, "text": slice_text})
                start += max(100, chunk_chars - overlap_chars)
            continue
        if buf and (buf_len + len(block) + 2) > chunk_chars:
            _flush()
        buf.append(block)
        buf_len += len(block) + 2
    _flush()
    return chunks


def load_persona_manifest(persona_path: Path) -> Dict[str, Any]:
    """Load optional `persona.yml` metadata (voice, language, aliases, replies)."""
    yml_path = persona_path / "persona.yml"
    data: Dict[str, Any] = {}
    if yml_path.is_file():
        try:
            loaded = yaml.safe_load(yml_path.read_text(encoding="utf-8", errors="replace")) or {}
            if isinstance(loaded, dict):
                data = dict(loaded)
        except Exception as exc:
            logger.debug("Failed to parse %s: %s", yml_path, exc)
    name = persona_path.name
    data.setdefault("id", name)
    data.setdefault("display_name", name.capitalize())
    data.setdefault("model", f"{name}:latest")
    data.setdefault("base_model", "nemotron-3.5-bolt:e4b")
    data.setdefault("response_language", "follow_user")
    data.setdefault("tts_language", "auto")
    data.setdefault("tts_voice", None)
    data.setdefault("tts_voice_en", "glados" if name.lower() == "glados" else None)
    data.setdefault("default_emotion", "neutral")
    aliases = data.get("aliases")
    if not isinstance(aliases, list):
        data["aliases"] = [name.lower()]
    else:
        data["aliases"] = [str(a).strip().lower() for a in aliases if str(a).strip()]
    return data


def load_persona_prompt_text(persona_path: Path) -> str:
    """Read `persona.txt`, ignoring comment lines."""
    txt_path = persona_path / "persona.txt"
    if not txt_path.is_file():
        return ""
    lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(line for line in lines if line.strip() and not line.lstrip().startswith("#")).strip()


def _safe_url_slug(url: str, title: str = "") -> str:
    raw_label = str(title or "").strip() or (url.rstrip("/").rsplit("/", 1)[-1] or "page")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_label).strip("_")[:60] or "page"
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{h}.md"


class PersonaRAG:
    """SQLite FTS5 + ONNX e5-small knowledge index for one persona directory."""

    def __init__(self, persona_dir: str | Path) -> None:
        self.persona_dir = Path(persona_dir)
        self.name = self.persona_dir.name
        self.db_path = self.persona_dir / "persona_rag.sqlite3"
        self.knowledge_dir = self.persona_dir / "knowledge"
        self.urls_path = self.persona_dir / "urls.txt"
        self._lock = threading.RLock()
        self._embed_fn: Optional[EmbedFn] = None
        self._fts_available = False
        self._conn = self._open_conn()
        self._init_db()
        self._hook_default_embedder()

    def _open_conn(self) -> sqlite3.Connection:
        self.persona_dir.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def _hook_default_embedder(self) -> None:
        try:
            from modules.cognitive_memory.services.embedding_hook import hook_embedding_provider

            hook_embedding_provider(self, name=f"persona_rag:{self.name}")
        except Exception:
            pass

    def set_embedding_provider(self, fn: Optional[EmbedFn]) -> None:
        self._embed_fn = fn

    def _init_db(self) -> None:
        with self._lock:
            con = self._conn
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS lore_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_hash TEXT UNIQUE,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    embedding BLOB,
                    embed_state INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            try:
                con.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS lore_fts USING fts5(id UNINDEXED, title, text, source)"
                )
                self._fts_available = True
            except sqlite3.OperationalError:
                self._fts_available = False
            con.commit()

    def _compute_embedding(self, text: str) -> Tuple[Optional[bytes], int]:
        if self._embed_fn is None:
            return None, 0
        try:
            vec = self._embed_fn(f"passage: {text}")
            if vec is not None:
                import numpy as np

                return np.asarray(vec, dtype="float32").tobytes(), 1
        except Exception:
            pass
        return None, 0

    def read_urls(self) -> List[str]:
        if not self.urls_path.is_file():
            return []
        urls: List[str] = []
        for raw in self.urls_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and line.startswith(("http://", "https://")):
                urls.append(line)
        return urls

    def fetch_urls_to_knowledge(self, *, force_fetch: bool = False, resolve_dns: bool = True) -> Dict[str, Any]:
        urls = self.read_urls()
        if not urls:
            return {"urls_total": 0, "fetched": 0, "skipped_cached": 0, "errors": []}
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        fetched = 0
        cached = 0
        errors: List[str] = []
        for url in urls:
            res = fetch_url_text(
                url,
                timeout_s=10.0,
                max_chars=24000,
                strip_mediawiki_noise=True,
                resolve_dns=resolve_dns,
            ) if force_fetch or not list(self.knowledge_dir.glob(f"*_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]}.md")) else None
            if res is None:
                cached += 1
                continue
            if res.get("ok") and res.get("text"):
                dest = self.knowledge_dir / _safe_url_slug(url, title=str(res.get("title") or ""))
                header = f"<!-- source: {res.get('url', url)} -->\n"
                dest.write_text(header + str(res["text"]), encoding="utf-8")
                fetched += 1
            else:
                errors.append(f"{url}: {res.get('error', 'fetch failed')}")
        return {"urls_total": len(urls), "fetched": fetched, "skipped_cached": cached, "errors": errors}

    def ingest(
        self,
        *,
        force_fetch: bool = False,
        fetch_urls: bool = True,
        clear_missing: bool = False,
        resolve_dns: bool = True,
    ) -> Dict[str, Any]:
        """Load local `knowledge/*.md|.txt` (and optional `urls.txt`) into SQLite+FTS5 index."""
        fetch_meta = (
            self.fetch_urls_to_knowledge(force_fetch=force_fetch, resolve_dns=resolve_dns)
            if fetch_urls
            else {"urls_total": len(self.read_urls()), "fetched": 0, "skipped_cached": 0, "errors": []}
        )
        files: List[Path] = []
        if self.knowledge_dir.is_dir():
            files = sorted(
                p for p in self.knowledge_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {".md", ".txt"}
            )
        all_chunks: List[Dict[str, str]] = []
        for fpath in files:
            raw = fpath.read_text(encoding="utf-8", errors="replace")
            all_chunks.extend(chunk_markdown(raw, source=fpath.name))

        inserted = 0
        kept = 0
        seen_hashes: set[str] = set()
        with self._lock:
            con = self._conn
            for chunk in all_chunks:
                text = chunk["text"].strip()
                if not text:
                    continue
                chash = hashlib.sha256(f"{chunk['source']}|{chunk['title']}|{text}".encode("utf-8")).hexdigest()[:24]
                seen_hashes.add(chash)
                existing = con.execute("SELECT id FROM lore_chunks WHERE chunk_hash = ?", (chash,)).fetchone()
                if existing is not None:
                    kept += 1
                    continue
                blob, est = self._compute_embedding(f"{chunk['title']} {text}".strip())
                cur = con.execute(
                    """
                    INSERT INTO lore_chunks (chunk_hash, source, title, text, embedding, embed_state)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (chash, chunk["source"], chunk["title"], text, blob, est),
                )
                row_id = int(cur.lastrowid or 0)
                if self._fts_available and row_id > 0:
                    con.execute(
                        "INSERT INTO lore_fts (id, title, text, source) VALUES (?, ?, ?, ?)",
                        (row_id, chunk["title"], text, chunk["source"]),
                    )
                inserted += 1

            if clear_missing and seen_hashes:
                rows = con.execute("SELECT id, chunk_hash FROM lore_chunks").fetchall()
                for row in rows:
                    if str(row["chunk_hash"]) not in seen_hashes:
                        con.execute("DELETE FROM lore_chunks WHERE id = ?", (int(row["id"]),))
                        if self._fts_available:
                            con.execute("DELETE FROM lore_fts WHERE id = ?", (int(row["id"]),))
            con.commit()

        return {
            "ok": True,
            "persona": self.name,
            "files": len(files),
            "chunks_total": inserted + kept,
            "inserted": inserted,
            "kept": kept,
            **fetch_meta,
        }

    def ensure_indexed(self) -> int:
        with self._lock:
            count = int(self._conn.execute("SELECT COUNT(*) FROM lore_chunks").fetchone()[0])
        if count > 0:
            return count
        has_local = self.knowledge_dir.is_dir() and any(
            p.suffix.lower() in {".md", ".txt"} for p in self.knowledge_dir.iterdir() if p.is_file()
        )
        if not has_local:
            return 0
        res = self.ingest(fetch_urls=False)
        return int(res.get("chunks_total", 0))

    def recall(self, query: str, *, limit: int = 3) -> List[Dict[str, Any]]:
        q = str(query or "").strip()
        if not q:
            return []
        self.ensure_indexed()
        k = max(1, min(12, int(limit)))
        q_tokens = set(_tokens(q))
        rows: List[sqlite3.Row] = []
        with self._lock:
            con = self._conn
            if self._fts_available and q_tokens:
                try:
                    fts_q = " OR ".join(f'"{t.replace(chr(34), "")}"' for t in sorted(q_tokens))
                    rows = con.execute(
                        """
                        SELECT c.* FROM lore_fts f JOIN lore_chunks c ON c.id = f.id
                        WHERE lore_fts MATCH ?
                        ORDER BY bm25(lore_fts)
                        LIMIT ?
                        """,
                        (fts_q, k * 5),
                    ).fetchall()
                except Exception:
                    rows = []
            if not rows or self._embed_fn is not None:
                extra = con.execute("SELECT * FROM lore_chunks LIMIT 120").fetchall()
                seen = {int(r["id"]) for r in rows}
                for r in extra:
                    if int(r["id"]) not in seen:
                        rows.append(r)
                        seen.add(int(r["id"]))

        if not rows:
            return []
        q_stems = _stem_tokens(q)
        scored: List[Dict[str, Any]] = []
        for row in rows:
            txt = str(row["text"] or "")
            title = str(row["title"] or "")
            source = str(row["source"] or "")
            page_label = re.sub(r"_[0-9a-f]{8}\.(?:md|txt)$", "", source).replace("_", " ").strip()
            toks = _stem_tokens(f"{page_label} {title} {txt}")
            src_stems = _stem_tokens(page_label)
            overlap = len(q_stems & toks) / max(1, len(q_stems)) if q_stems else 0.0
            src_boost = 0.25 * (len(q_stems & src_stems) / max(1, len(src_stems))) if (q_stems and src_stems) else 0.0
            scored.append(
                {
                    "id": int(row["id"]),
                    "source": source,
                    "page": page_label,
                    "title": title,
                    "text": txt,
                    "score": round(min(1.0, float(overlap) + src_boost), 4),
                    "_blob": row["embedding"],
                }
            )
        semantic = self._semantic_rerank(q, scored)
        for item in scored:
            item.pop("_blob", None)
            if semantic is not None and item["id"] in semantic:
                sem = max(0.0, float(semantic[item["id"]]))
                item["semantic"] = round(sem, 4)
                item["score"] = round(max(0.0, min(1.0, 0.35 * item["score"] + 0.65 * sem)), 4)
        scored.sort(key=lambda x: x["score"], reverse=True)
        return [item for item in scored[:k] if item["score"] > 0.05]

    def _semantic_rerank(self, query: str, scored: List[Dict[str, Any]]) -> Optional[Dict[int, float]]:
        if self._embed_fn is None or not scored:
            return None
        try:
            import numpy as np

            q_vec = np.asarray(self._embed_fn(f"query: {query}"), dtype="float32")
            q_vec = q_vec / max(1e-9, float(np.linalg.norm(q_vec)))
            ids: List[int] = []
            vecs: List[Any] = []
            for item in scored:
                blob = item.get("_blob")
                if not blob:
                    continue
                v = np.frombuffer(blob, dtype="float32")
                if v.shape != q_vec.shape:
                    continue
                vecs.append(v / max(1e-9, float(np.linalg.norm(v))))
                ids.append(int(item["id"]))
            if not vecs:
                return None
            sims = np.asarray(vecs, dtype="float32") @ q_vec
            out: Dict[int, float] = {}
            for cid, raw_s in zip(ids, sims):
                s = float(raw_s)
                out[cid] = max(0.0, min(1.0, (s - 0.72) / 0.18)) if s > 0.65 else max(0.0, s)
            return out
        except Exception:
            return None

    def build_prompt_context(self, query: str, *, limit: int = 3) -> str:
        hits = self.recall(query, limit=limit)
        if not hits:
            return ""
        lines: List[str] = []
        for h in hits:
            page = str(h.get("page") or "").strip()
            sec = str(h.get("title") or "").strip()
            if page and sec and page.lower() not in sec.lower():
                tag = f"[{page} — {sec}] "
            elif sec or page:
                tag = f"[{sec or page}] "
            else:
                tag = ""
            lines.append(f"- {tag}{h['text']}")
        return (
            f"[PERSONA LORE & KNOWLEDGE ({self.name})]\n"
            "Use these character-specific facts naturally when relevant:\n"
            + "\n".join(lines)
        )

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = int(self._conn.execute("SELECT COUNT(*) FROM lore_chunks").fetchone()[0])
            embedded = int(self._conn.execute("SELECT COUNT(*) FROM lore_chunks WHERE embed_state = 1").fetchone()[0])
        return {
            "persona": self.name,
            "db_path": str(self.db_path),
            "chunks": total,
            "embedded": embedded,
            "urls": len(self.read_urls()),
        }


class PersonaManager:
    """Discovers personas, caches PersonaRAG instances, and resolves spoken aliases."""

    def __init__(self, base_dir: str | Path = _DEFAULT_PERSONA_DIR) -> None:
        self.base_dir = Path(base_dir)
        self._lock = threading.RLock()
        self._rags: Dict[str, PersonaRAG] = {}

    def list_personas(self) -> List[Dict[str, Any]]:
        if not self.base_dir.is_dir():
            return []
        items: List[Dict[str, Any]] = []
        for entry in sorted(self.base_dir.iterdir()):
            if entry.is_dir() and _SAFE_NAME_RE.match(entry.name):
                manifest = load_persona_manifest(entry)
                manifest["has_persona_txt"] = (entry / "persona.txt").is_file()
                manifest["has_urls"] = (entry / "urls.txt").is_file()
                items.append(manifest)
        return items

    def get_persona_dir(self, name: str) -> Path:
        cleaned = str(name or "").strip()
        if not cleaned or not _SAFE_NAME_RE.match(cleaned):
            raise ValueError(f"invalid persona name: {name!r}")
        target = (self.base_dir / cleaned).resolve()
        root = self.base_dir.resolve()
        if not target.is_relative_to(root):
            raise ValueError("persona path escapes base directory")
        return target

    def resolve_name(self, query_or_name: str) -> Optional[str]:
        low = str(query_or_name or "").strip().lower()
        if not low:
            return None
        for item in self.list_personas():
            pid = str(item.get("id", "")).lower()
            if low == pid or low == str(item.get("display_name", "")).lower():
                return str(item["id"])
            if low in (item.get("aliases") or []):
                return str(item["id"])
        return None

    def load_persona(self, name: str) -> Dict[str, Any]:
        resolved = self.resolve_name(name) or str(name or "").strip()
        pdir = self.get_persona_dir(resolved)
        if not pdir.is_dir():
            raise FileNotFoundError(f"persona '{resolved}' not found under {self.base_dir}")
        manifest = load_persona_manifest(pdir)
        prompt_text = load_persona_prompt_text(pdir)
        rag = self.get_rag(pdir.name)
        rag.ensure_indexed()
        return {
            "name": pdir.name,
            "dir": str(pdir),
            "manifest": manifest,
            "prompt_text": prompt_text,
            "rag": rag,
        }

    def get_rag(self, name: str) -> PersonaRAG:
        pdir = self.get_persona_dir(name)
        with self._lock:
            rag = self._rags.get(pdir.name)
            if rag is None:
                rag = PersonaRAG(pdir)
                self._rags[pdir.name] = rag
            return rag

    def ensure_ollama_model(
        self,
        name: str,
        *,
        base_url: str = "",
        client: Any = None,
        timeout_s: float = 90.0,
    ) -> Dict[str, Any]:
        """Build or update this persona's derived Ollama model (FROM nemotron-3.5-bolt:e4b) on remote Ollama."""
        from modules.common.ollama_modelfile import (
            DEFAULT_BASE_MODEL,
            create_remote_ollama_model,
            load_or_build_persona_modelfile,
        )

        pdir = self.get_persona_dir(name)
        manifest = load_persona_manifest(pdir)
        model_name = str(manifest.get("model") or f"{pdir.name}:latest").strip()
        base_model = str(manifest.get("base_model") or DEFAULT_BASE_MODEL).strip()
        modelfile_text = load_or_build_persona_modelfile(pdir, base_model=base_model)
        if client is not None and hasattr(client, "create_model"):
            ok = bool(client.create_model(model_name, modelfile_text))
            return {
                "ok": ok,
                "persona": pdir.name,
                "model": model_name,
                "base_model": base_model,
                "detail": "client.create_model",
            }
        target_url = str(base_url or "").strip()
        if not target_url:
            try:
                from modules.common.config_loader import load_agent_config

                cfg = load_agent_config()
                target_url = str(
                    (cfg.get("ollama") or {}).get("base_url")
                    or (cfg.get("agent") or {}).get("ollama_base_url")
                    or ""
                ).strip()
            except Exception:
                target_url = ""
        ok, detail = create_remote_ollama_model(
            model_name,
            modelfile_text,
            base_url=target_url,
            timeout_s=timeout_s,
        )
        return {
            "ok": ok,
            "persona": pdir.name,
            "model": model_name,
            "base_model": base_model,
            "base_url": target_url,
            "detail": detail,
        }

    def create_persona(
        self,
        name: str,
        instructions: str,
        *,
        urls: Optional[List[str]] = None,
        base_model: str = "nemotron-3.5-bolt:e4b",
        display_name: str = "",
        response_language: str = "follow_user",
        tts_voice: Optional[str] = None,
        tts_voice_en: Optional[str] = None,
        default_emotion: str = "neutral",
        aliases: Optional[List[str]] = None,
        create_model: bool = True,
        ollama_base_url: str = "",
        ollama_client: Any = None,
        fetch_urls: bool = True,
    ) -> Dict[str, Any]:
        """Create a complete persona folder (`persona.txt`, `persona.yml`, `modelfile`, `urls.txt`, RAG) and push its Ollama model."""
        from modules.common.ollama_modelfile import DEFAULT_BASE_MODEL, render_persona_modelfile

        pdir = self.get_persona_dir(name)
        pid = pdir.name
        bmodel = str(base_model or DEFAULT_BASE_MODEL).strip()
        model_tag = f"{pid}:latest"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "persona.txt").write_text(str(instructions or "").strip() + "\n", encoding="utf-8")

        alias_list = list(dict.fromkeys([pid.lower(), *(str(a).strip().lower() for a in (aliases or []) if str(a).strip())]))
        manifest_data: Dict[str, Any] = {
            "id": pid,
            "display_name": display_name or pid.capitalize(),
            "model": model_tag,
            "base_model": bmodel,
            "response_language": response_language or "follow_user",
            "tts_language": "auto",
            "tts_voice": tts_voice,
            "tts_voice_en": tts_voice_en,
            "default_emotion": default_emotion or "neutral",
            "aliases": alias_list,
        }
        (pdir / "persona.yml").write_text(
            yaml.safe_dump(manifest_data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        modelfile_txt = render_persona_modelfile(pid, instructions, base_model=bmodel)
        (pdir / "modelfile").write_text(modelfile_txt, encoding="utf-8")

        clean_urls = [str(u).strip() for u in (urls or []) if str(u).strip().startswith(("http://", "https://"))]
        if clean_urls or not (pdir / "urls.txt").is_file():
            (pdir / "urls.txt").write_text("\n".join(clean_urls) + ("\n" if clean_urls else ""), encoding="utf-8")

        rag = self.get_rag(pid)
        ingest_res = rag.ingest(fetch_urls=bool(fetch_urls and clean_urls))
        model_res: Dict[str, Any] = {"ok": None, "model": model_tag, "base_model": bmodel}
        if create_model:
            model_res = self.ensure_ollama_model(
                pid,
                base_url=ollama_base_url,
                client=ollama_client,
            )
        return {
            "ok": True,
            "persona": pid,
            "model": model_tag,
            "base_model": bmodel,
            "ingest": ingest_res,
            "ollama_create": model_res,
        }

    def close(self) -> None:
        with self._lock:
            for rag in self._rags.values():
                rag.close()
            self._rags.clear()


__all__ = [
    "PersonaManager",
    "PersonaRAG",
    "chunk_markdown",
    "load_persona_manifest",
    "load_persona_prompt_text",
]
