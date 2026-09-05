from __future__ import annotations

from ..models import (
    Palette,
    Snapshot,
    UIState,
    event_line,
    hbar,
    newest_first_events,
)


def render_logs(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    events = newest_first_events(snapshot, ui)
    if events:
        ui.selected_event = min(max(0, ui.selected_event), len(events) - 1)
    header = (
        f"view:{ui.log_view}  filter:{ui.filter_text or '<none>'}  "
        f"events:{len(events)}  selected:{ui.selected_event+1 if events else 0}  hidden-noise:{snapshot.hidden_noise}"
    )
    lines = [
        pal.dim(header),
        pal.dim("Newest first. Up/Down selects, v cycles human/full/warn, / filters."),
        "",
    ]
    usable = max(0, height - 3)
    start = min(max(0, ui.scroll), max(0, len(events) - 1))
    visible = events[start : start + usable]
    for row, ev in enumerate(visible, start):
        prefix = "> " if row == ui.selected_event else "  "
        line = event_line(ev, max(1, width - 2), pal)
        lines.append(prefix + line[: max(1, width - 2)])
    if not visible:
        lines.append("  no events match current view/filter")
    return lines[:height]


def render_signals(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines: list[str] = []
    lines.append(pal.bold("Polls vs real work"))
    lines.append(
        "/vlm/context/latest and /vlm/results/latest are cache/result polls, not necessarily expensive VLM inference."
    )
    lines.append("/arduino/request is command/bridge traffic; on PC tests it may be synthetic or degraded.")
    lines.append("")
    top = snapshot.endpoints.most_common(14)
    max_count = top[0][1] if top else 1
    lines.append(pal.bold("HTTP endpoints"))
    for ep, count in top:
        kind = (
            "poll"
            if ep
            in {
                "/vlm/context/latest",
                "/vlm/results/latest",
                "/state/get",
                "/speech/last",
                "/speech/direction",
                "/arduino/request",
            }
            else "action"
        )
        lines.append(f" {ep:<34} {kind:<6} {hbar(count, max_count, 18, pal)} {count}")
    lines.append("")
    lines.append(pal.bold("Remote hosts"))
    if snapshot.remote_hosts:
        for host, count in snapshot.remote_hosts.most_common(8):
            lines.append(
                f" {host:<22} {hbar(count, max(snapshot.remote_hosts.values()), 18, pal)} {count}"
            )
    else:
        lines.append(" no remote host activity detected")
    return lines[:height]
