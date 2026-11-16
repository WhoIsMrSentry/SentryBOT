from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


def _format_ts(raw_ts: Any) -> str:
    if raw_ts is None or raw_ts == "":
        return "unknown"
    try:
        val = float(raw_ts)
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(val))
    except (TypeError, ValueError, OSError):
        return str(raw_ts)[:19]


class MemoryExplorerModal(ModalScreen[None]):
    """Interactive Cognitive Memory, SocialDB & World Memory Explorer Dialog."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("m", "dismiss", "Close"),
    ]

    def __init__(self, root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.db_path = root / "data" / "social.sqlite3"
        self.world_db_path = root / "data" / "world_memory.sqlite3"
        self.active_tab = "social"

    def compose(self) -> ComposeResult:
        with Vertical(id="memory_dialog"):
            yield Label("■ SENTRYBOT COGNITIVE MEMORY & SOCIAL DB EXPLORER", id="memory_title", markup=False)

            with Horizontal(id="memory_tab_bar"):
                yield Button("SocialDB", id="memory_tab_social", classes="memory_tab_btn", variant="primary")
                yield Button("WorldMemory", id="memory_tab_world", classes="memory_tab_btn", variant="default")

            with Horizontal(id="memory_search_bar"):
                yield Input(placeholder="Search memory, entities, emotions, or sightings...", id="memory_query_input")
                yield Button("Search", id="memory_search_btn", variant="primary")
                yield Button("Refresh", id="memory_refresh_btn", variant="default")

            with VerticalScroll(id="memory_scroll"):
                yield Static(id="memory_content")

            yield Button("Close (Esc / m)", id="memory_close_btn", variant="primary")

    def on_mount(self) -> None:
        self.load_memory_records()

    def _apply_memory_content(self, rendered: Text | str) -> None:
        try:
            self.query_one("#memory_content", Static).update(rendered)
        except Exception:
            pass

    def _build_social_renderable(self, query: str = "") -> Text | str:
        if not self.db_path.exists():
            return (
                f"SocialDB file not found at: {self.db_path}\n"
                "Memory will be initialized automatically when robot runtime starts."
            )

        try:
            conn = sqlite3.connect(str(self.db_path), timeout=2.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            rich_text = Text()
            rich_text.append(
                f"Database: {self.db_path.name}  |  File Size: {self.db_path.stat().st_size:,} bytes\n\n",
                style="bold #FA1E4E",
            )

            # 1. Sightings (schema: person_id, ts, source, mood, distance_m joined with persons)
            try:
                if query:
                    like = f"%{query}%"
                    cursor.execute(
                        """
                        SELECT COALESCE(NULLIF(p.display_name, ''), p.canonical_name, s.person_id) AS person_name,
                               s.person_id, s.ts, s.source, s.mood, s.distance_m
                        FROM sightings s
                        LEFT JOIN persons p ON s.person_id = p.id
                        WHERE s.person_id LIKE ?
                           OR COALESCE(p.canonical_name, '') LIKE ?
                           OR COALESCE(p.display_name, '') LIKE ?
                           OR s.mood LIKE ?
                           OR s.source LIKE ?
                        ORDER BY s.ts DESC, s.id DESC LIMIT 10
                        """,
                        (like, like, like, like, like),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT COALESCE(NULLIF(p.display_name, ''), p.canonical_name, s.person_id) AS person_name,
                               s.person_id, s.ts, s.source, s.mood, s.distance_m
                        FROM sightings s
                        LEFT JOIN persons p ON s.person_id = p.id
                        ORDER BY s.ts DESC, s.id DESC LIMIT 8
                        """
                    )
                sightings = cursor.fetchall()
                rich_text.append("─── RECENT FACE SIGHTINGS & TRACKS ───────────────────────────\n", style="bold #a88d94")
                if sightings:
                    for row in sightings:
                        ts = _format_ts(row["ts"])
                        name = row["person_name"] or row["person_id"] or "Unknown"
                        src = row["source"] or "camera"
                        mood = row["mood"] or "neutral"
                        dist_raw = row["distance_m"]
                        dist_txt = f"{float(dist_raw):4.2f}m" if dist_raw is not None else "N/A"
                        rich_text.append(f"• [{ts}] ", style="dim")
                        rich_text.append(f"{str(name):<16} ", style="bold cyan")
                        rich_text.append(f"Src: {src} | Mood: {mood} | Dist: {dist_txt}\n", style="white")
                else:
                    rich_text.append("• No sighting records found.\n", style="dim")
            except Exception as e:
                rich_text.append(f"Sightings table query note: {e}\n", style="dim")

            rich_text.append("\n")

            # 2. Owner Sessions (schema: id, start_ts, end_ts, source, authority_level, notes)
            try:
                if query:
                    like = f"%{query}%"
                    cursor.execute(
                        """
                        SELECT id, start_ts, end_ts, source, authority_level, notes
                        FROM owner_sessions
                        WHERE source LIKE ? OR notes LIKE ?
                        ORDER BY start_ts DESC, id DESC LIMIT 5
                        """,
                        (like, like),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, start_ts, end_ts, source, authority_level, notes
                        FROM owner_sessions
                        ORDER BY start_ts DESC, id DESC LIMIT 5
                        """
                    )
                sessions = cursor.fetchall()
                rich_text.append("─── OWNER SESSIONS ───────────────────────────────────────────\n", style="bold #a88d94")
                if sessions:
                    for row in sessions:
                        s_id = row["id"]
                        start = _format_ts(row["start_ts"])
                        src = row["source"] or "local"
                        auth = int(row["authority_level"] or 0)
                        is_active = row["end_ts"] is None
                        act = "ACTIVE" if is_active else "CLOSED"
                        rich_text.append(f"• [{start}] ", style="dim")
                        rich_text.append(
                            f"Session #{s_id} ({src}, auth={auth}): ",
                            style="bold green" if is_active else "white",
                        )
                        rich_text.append(f"Status: {act}\n", style="bold" if is_active else "dim")
                else:
                    rich_text.append("• No owner session records found.\n", style="dim")
            except Exception as e:
                rich_text.append(f"Owner sessions table query note: {e}\n", style="dim")

            rich_text.append("\n")

            # 3. Mood Snapshots (schema: ts, happiness, energy, curiosity, fear, dominant)
            try:
                if query:
                    cursor.execute(
                        """
                        SELECT ts, happiness, energy, curiosity, fear, dominant
                        FROM mood_snapshots
                        WHERE dominant LIKE ?
                        ORDER BY ts DESC LIMIT 6
                        """,
                        (f"%{query}%",),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT ts, happiness, energy, curiosity, fear, dominant
                        FROM mood_snapshots
                        ORDER BY ts DESC LIMIT 6
                        """
                    )
                moods = cursor.fetchall()
                rich_text.append("─── HOMEOSTATIC MOOD & EMOTION TIMELINE ──────────────────────\n", style="bold #a88d94")
                if moods:
                    for row in moods:
                        ts = _format_ts(row["ts"])
                        dom = str(row["dominant"] or "neutral").capitalize()
                        happy = row["happiness"]
                        energy = row["energy"]
                        curiosity = row["curiosity"]
                        fear = row["fear"]
                        h_txt = f"{float(happy):.2f}" if happy is not None else "N/A"
                        e_txt = f"{float(energy):.2f}" if energy is not None else "N/A"
                        c_txt = f"{float(curiosity):.2f}" if curiosity is not None else "N/A"
                        f_txt = f"{float(fear):.2f}" if fear is not None else "N/A"
                        rich_text.append(f"• [{ts}] ", style="dim")
                        rich_text.append(f"{dom:<12} ", style="bold yellow")
                        rich_text.append(
                            f"Happy: {h_txt} | Energy: {e_txt} | Curiosity: {c_txt} | Fear: {f_txt}\n",
                            style="white",
                        )
                else:
                    rich_text.append("• No mood snapshots recorded yet.\n", style="dim")
            except Exception as e:
                rich_text.append(f"Mood snapshots table query note: {e}\n", style="dim")

            conn.close()
            return rich_text
        except Exception as exc:
            return f"Error querying SocialDB: {exc}"

    def _resolve_world_db_path(self) -> Optional[Path]:
        if self.world_db_path.exists():
            return self.world_db_path
        if self.db_path.exists():
            return self.db_path
        return None

    def _build_world_memory_renderable(self, query: str = "") -> Text | str:
        db_target = self._resolve_world_db_path()
        if db_target is None:
            return (
                f"WorldMemory database not found at: {self.world_db_path} (or {self.db_path})\n"
                "World memories will be persisted once observations are recorded."
            )

        try:
            conn = sqlite3.connect(str(db_target), timeout=2.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            rich_text = Text()
            rich_text.append(
                f"World Memory Source: {db_target.name}  |  File Size: {db_target.stat().st_size:,} bytes\n\n",
                style="bold #FA1E4E",
            )

            try:
                if query:
                    like = f"%{query}%"
                    cursor.execute(
                        """
                        SELECT id, kind, name, summary, source, confidence, salience,
                               observation_count, last_seen, location
                        FROM world_memories
                        WHERE name LIKE ? OR summary LIKE ? OR kind LIKE ? OR location LIKE ?
                        ORDER BY last_seen DESC LIMIT 12
                        """,
                        (like, like, like, like),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, kind, name, summary, source, confidence, salience,
                               observation_count, last_seen, location
                        FROM world_memories
                        ORDER BY last_seen DESC LIMIT 10
                        """
                    )
                memories = cursor.fetchall()
                rich_text.append("─── WORLD MEMORIES & ENTITIES ────────────────────────────────\n", style="bold #a88d94")
                if memories:
                    for row in memories:
                        ts = _format_ts(row["last_seen"])
                        kind = str(row["kind"] or "fact").upper()
                        name = str(row["name"] or row["id"] or "Unnamed")
                        summary = str(row["summary"] or "").strip()
                        conf = float(row["confidence"] or 0.0)
                        obs_cnt = int(row["observation_count"] or 1)
                        loc = str(row["location"] or "").strip()
                        loc_suffix = f" @ {loc}" if loc else ""
                        rich_text.append(f"• [{ts}] ", style="dim")
                        rich_text.append(f"[{kind}] {name}{loc_suffix} ", style="bold cyan")
                        rich_text.append(f"(conf={conf:.2f}, seen={obs_cnt}x)\n", style="white")
                        if summary:
                            rich_text.append(f"  {summary[:110]}\n", style="dim")
                else:
                    rich_text.append("• No world memory records found.\n", style="dim")
            except Exception as e:
                rich_text.append(f"World memories table query note: {e}\n", style="dim")

            rich_text.append("\n")

            try:
                if query:
                    like = f"%{query}%"
                    cursor.execute(
                        """
                        SELECT wo.ts, wo.memory_id, wo.source, wo.text
                        FROM world_observations wo
                        LEFT JOIN world_memories wm ON wo.memory_id = wm.id
                        WHERE wo.text LIKE ?
                           OR wo.memory_id LIKE ?
                           OR wo.source LIKE ?
                           OR COALESCE(wm.name, '') LIKE ?
                           OR COALESCE(wm.summary, '') LIKE ?
                        ORDER BY wo.ts DESC LIMIT 8
                        """,
                        (like, like, like, like, like),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT ts, memory_id, source, text
                        FROM world_observations
                        ORDER BY ts DESC LIMIT 6
                        """
                    )
                observations = cursor.fetchall()
                rich_text.append("─── RECENT WORLD OBSERVATIONS ────────────────────────────────\n", style="bold #a88d94")
                if observations:
                    for row in observations:
                        ts = _format_ts(row["ts"])
                        src = str(row["source"] or "sensor")
                        text = str(row["text"] or "").strip()
                        rich_text.append(f"• [{ts}] ", style="dim")
                        rich_text.append(f"[{src}] ", style="bold yellow")
                        rich_text.append(f"{text[:110]}\n", style="white")
                else:
                    rich_text.append("• No recent world observations found.\n", style="dim")
            except Exception as e:
                rich_text.append(f"World observations table query note: {e}\n", style="dim")

            conn.close()
            return rich_text
        except Exception as exc:
            return f"Error querying WorldMemory DB: {exc}"

    def _build_memory_renderable(self, query: str = "", tab: Optional[str] = None) -> Text | str:
        target_tab = (tab or self.active_tab).strip().lower()
        if target_tab == "world":
            return self._build_world_memory_renderable(query=query)
        return self._build_social_renderable(query=query)

    @work(thread=True, exclusive=True)
    def _load_memory_worker(self, query: str = "", tab: str = "social") -> None:
        rendered = self._build_memory_renderable(query=query, tab=tab)
        self.app.call_from_thread(self._apply_memory_content, rendered)

    def load_memory_records(self, query: str = "", tab: Optional[str] = None) -> None:
        if tab is not None:
            self.active_tab = tab
        if self.is_mounted:
            try:
                _ = self.app
                self._load_memory_worker(query=query, tab=self.active_tab)
                return
            except Exception:
                pass
        rendered = self._build_memory_renderable(query=query, tab=self.active_tab)
        self._apply_memory_content(rendered)

    def _switch_tab(self, tab: str) -> None:
        self.active_tab = tab
        try:
            social_btn = self.query_one("#memory_tab_social", Button)
            world_btn = self.query_one("#memory_tab_world", Button)
            social_btn.variant = "primary" if tab == "social" else "default"
            world_btn.variant = "primary" if tab == "world" else "default"
        except Exception:
            pass
        try:
            query = self.query_one("#memory_query_input", Input).value.strip()
        except Exception:
            query = ""
        self.load_memory_records(query=query, tab=tab)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "memory_close_btn":
            self.dismiss()
        elif btn_id == "memory_tab_social":
            self._switch_tab("social")
        elif btn_id == "memory_tab_world":
            self._switch_tab("world")
        elif btn_id == "memory_refresh_btn":
            try:
                query = self.query_one("#memory_query_input", Input).value.strip()
            except Exception:
                query = ""
            self.load_memory_records(query=query)
        elif btn_id == "memory_search_btn":
            query = self.query_one("#memory_query_input", Input).value.strip()
            self.load_memory_records(query=query)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "memory_query_input":
            query = event.value.strip()
            self.load_memory_records(query=query)

