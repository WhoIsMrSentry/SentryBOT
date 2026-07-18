from __future__ import annotations

from .event_bus import RuntimeEvent
from .renderer import ConsoleRenderer


def render_startup_panel(renderer: ConsoleRenderer, *, mode: str = "dashboard") -> str:
    lines = [
        "Runtime console initialized",
        "",
        f"Mode        {mode}",
        "Display     ASCII panels, no logo art",
        "Noise       background health/polling requests hidden from console",
        "Trace       log file remains detailed; console shows human events",
        "",
        "Keys        Ctrl+C stops the robot runtime",
    ]
    return renderer.box("SENTRYBOT RUNTIME", lines)


def render_event_panel(renderer: ConsoleRenderer, events: list[RuntimeEvent]) -> str:
    if not events:
        return renderer.box("EVENT STREAM", ["waiting for runtime events..."])
    return renderer.box("EVENT STREAM", [renderer.event_line(event) for event in events])


def render_warning_panel(renderer: ConsoleRenderer, event: RuntimeEvent) -> str:
    details = []
    for key, value in sorted(event.details.items()):
        details.append(f"{key:<12} {value}")
    lines = [
        f"Component   {event.component or event.channel}",
        f"Level       {event.level}",
        f"Problem     {event.message}",
    ]
    if event.reason:
        lines.append(f"Reason      {event.reason}")
    if details:
        lines.append("")
        lines.extend(details)
    return renderer.box(event.level, lines)


def render_summary_panel(renderer: ConsoleRenderer, message: str) -> str:
    return renderer.box("SYSTEM", [message])
