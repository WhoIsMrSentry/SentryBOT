from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class MemoryExplorerModal(ModalScreen[None]):
    """Interactive Cognitive Memory & Social DB Explorer Dialog."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("m", "dismiss", "Close"),
    ]

    def __init__(self, root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.db_path = root / "data" / "social.sqlite3"

    def compose(self) -> ComposeResult:
        with Vertical(id="memory_dialog"):
            yield Label("■ SENTRYBOT COGNITIVE MEMORY & SOCIAL DB EXPLORER", id="memory_title", markup=False)

            with Horizontal(id="memory_search_bar"):
                yield Input(placeholder="Search memory, entities, emotions, or sightings...", id="memory_query_input")
                yield Button("Search", id="memory_search_btn", variant="primary")
                yield Button("Refresh", id="memory_refresh_btn", variant="default")

            with VerticalScroll(id="memory_scroll"):
                yield Static(id="memory_content")

            yield Button("Close (Esc / m)", id="memory_close_btn", variant="primary")

    def on_mount(self) -> None:
        self.load_memory_records()

    def load_memory_records(self, query: str = "") -> None:
        content = self.query_one("#memory_content", Static)
        if not self.db_path.exists():
            content.update(
                f"SocialDB file not found at: {self.db_path}\n"
                "Memory will be initialized automatically when robot runtime starts."
            )
            return

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            rich_text = Text()
            rich_text.append(f"Database: {self.db_path.name}  |  File Size: {self.db_path.stat().st_size:,} bytes\n\n", style="bold #FA1E4E")

            # 1. Sightings
            try:
                if query:
                    cursor.execute(
                        "SELECT person_name, confidence, distance_m, created_at FROM sightings WHERE person_name LIKE ? ORDER BY id DESC LIMIT 10",
                        (f"%{query}%",),
                    )
                else:
                    cursor.execute("SELECT person_name, confidence, distance_m, created_at FROM sightings ORDER BY id DESC LIMIT 8")
                sightings = cursor.fetchall()
                rich_text.append("─── RECENT FACE SIGHTINGS & TRACKS ───────────────────────────\n", style="bold #a88d94")
                if sightings:
                    for row in sightings:
                        ts = str(row["created_at"])[:19]
                        name = row["person_name"] or "Unknown"
                        conf = float(row["confidence"] or 0.0)
                        dist = float(row["distance_m"] or 0.0)
                        rich_text.append(f"• [{ts}] ", style="dim")
                        rich_text.append(f"{name:<16} ", style="bold cyan")
                        rich_text.append(f"Conf: {conf:4.2f} | Dist: {dist:4.2f}m\n", style="white")
                else:
                    rich_text.append("• No sighting records found.\n", style="dim")
            except Exception as e:
                rich_text.append(f"Sightings table query note: {e}\n", style="dim")

            rich_text.append("\n")

            # 2. Owner Sessions
            try:
                cursor.execute("SELECT session_id, owner_name, started_at, is_active FROM owner_sessions ORDER BY id DESC LIMIT 5")
                sessions = cursor.fetchall()
                rich_text.append("─── OWNER SESSIONS ───────────────────────────────────────────\n", style="bold #a88d94")
                if sessions:
                    for row in sessions:
                        s_id = str(row["session_id"])[:8]
                        owner = row["owner_name"] or "Owner"
                        start = str(row["started_at"])[:19]
                        act = "ACTIVE" if row["is_active"] else "CLOSED"
                        rich_text.append(f"• [{start}] ", style="dim")
                        rich_text.append(f"Session {s_id} ({owner}): ", style="bold green" if act == "ACTIVE" else "white")
                        rich_text.append(f"Status: {act}\n", style="bold" if act == "ACTIVE" else "dim")
                else:
                    rich_text.append("• No owner session records found.\n", style="dim")
            except Exception as e:
                rich_text.append(f"Owner sessions table query note: {e}\n", style="dim")

            rich_text.append("\n")

            # 3. Mood Snapshots
            try:
                cursor.execute("SELECT emotion, valence, arousal, dominant_need, created_at FROM mood_snapshots ORDER BY id DESC LIMIT 6")
                moods = cursor.fetchall()
                rich_text.append("─── HOMEOSTATIC MOOD & EMOTION TIMELINE ───────────────────────\n", style="bold #a88d94")
                if moods:
                    for row in moods:
                        ts = str(row["created_at"])[:19]
                        em = str(row["emotion"]).capitalize()
                        v = float(row["valence"] or 0.0)
                        a = float(row["arousal"] or 0.0)
                        need = str(row["dominant_need"] or "curiosity").capitalize()
                        rich_text.append(f"• [{ts}] ", style="dim")
                        rich_text.append(f"{em:<12} ", style="bold yellow")
                        rich_text.append(f"Valence: {v:+4.2f} | Arousal: {a:+4.2f} | Need: {need}\n", style="white")
                else:
                    rich_text.append("• No mood snapshots recorded yet.\n", style="dim")
            except Exception as e:
                rich_text.append(f"Mood snapshots table query note: {e}\n", style="dim")

            conn.close()
            content.update(rich_text)
        except Exception as exc:
            content.update(f"Error querying SocialDB: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "memory_close_btn":
            self.dismiss()
        elif btn_id == "memory_refresh_btn":
            self.load_memory_records()
        elif btn_id == "memory_search_btn":
            query = self.query_one("#memory_query_input", Input).value.strip()
            self.load_memory_records(query)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "memory_query_input":
            query = event.value.strip()
            self.load_memory_records(query)

