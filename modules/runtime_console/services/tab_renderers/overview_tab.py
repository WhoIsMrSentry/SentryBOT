from __future__ import annotations

from typing import Any

from ..models import (
    APP,
    TABS,
    VERSION,
    Palette,
    ServiceStatus,
    Snapshot,
    UIState,
    box,
    clean_path,
    crop,
    dict_get,
    fit,
    hbar,
    health_summary_for,
    is_pc_expected,
    selected_event,
    service_card,
    service_is_pc_expected,
    suggested_fix,
    visible_len,
)
from ..robot_process import _expression_core


def _score_bar(value: object, width: int = 18) -> str:
    try:
        val = max(0.0, min(100.0, float(value)))
    except Exception:
        val = 0.0
    filled = int(round((val / 100.0) * width))
    return "#" * filled + "." * max(0, width - filled)


def draw_header(width: int, snapshot: Snapshot, ui: UIState, robot_status: str, pal: Palette) -> str:
    errs, warns, oks, pc_count = health_summary_for(snapshot, ui)
    profile = "PC TEST" if ui.profile == "pc-test" else "ROBOT"
    left = pal.bold(f" {APP} CONTROL CENTER ")
    mid = f"{VERSION} | {profile} | {robot_status} | up {snapshot.uptime}"
    right = (
        f"OK:{oks} PC:{pc_count} WARN:{warns} ERR:{errs}"
        if pc_count
        else f"OK:{oks} WARN:{warns} ERR:{errs}"
    )
    room = width - visible_len(left) - len(mid) - len(right) - 2
    if room < 1:
        mid = crop(mid, max(10, width - visible_len(left) - len(right) - 4))
        room = width - visible_len(left) - len(mid) - len(right) - 2
    return fit(left + " " + mid + " " * max(1, room) + right, width)


def draw_sidebar(
    height: int, width: int, ui: UIState, snapshot: Snapshot, pal: Palette, ascii_mode: bool
) -> list[str]:
    lines: list[str] = []
    for idx, tab in enumerate(TABS):
        prefix = f"{idx+1}" if idx < 9 else " "
        marker = ">" if idx == ui.active_tab else " "
        label = f" {marker} {prefix} {tab}"
        lines.append(pal.cyan(label) if idx == ui.active_tab else label)
    lines.append("")
    lines.append(pal.dim("Health"))
    for name in ["CORE", "AI", "VISION", "AUDIO", "TTS", "MOVE"]:
        svc = snapshot.services.get(name, ServiceStatus(name))
        state = "PC" if ui.profile == "pc-test" and service_is_pc_expected(name, svc) else svc.state
        lines.append(f" {name:<7} {pal.level(state):<12}")
    lines.append("")
    lines.append(pal.dim("Hotkeys"))
    for item in ["/ filter", "v view", "s search", "e edit", ": command", "r refresh", "q quit"]:
        lines.append(" " + item)
    return box("NAVIGATOR", lines, width, height, pal, ascii_mode)


def render_overview(
    width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette, ascii_mode: bool
) -> list[str]:
    lines: list[str] = []
    errs, warns, oks, pc_count = health_summary_for(snapshot, ui)
    mode = "PC TEST MODE" if ui.profile == "pc-test" else "ROBOT MODE"
    lines.append(
        f"{pal.yellow(mode) if ui.profile == 'pc-test' else pal.green(mode)}  services OK:{oks} PC:{pc_count} WARN:{warns} ERR:{errs}  uptime:{snapshot.uptime}"
    )
    lines.append(pal.dim("Hardware-missing warnings are grouped separately during PC tests."))
    lines.append("")

    names = ["CORE", "AI", "VISION", "AUDIO", "TTS", "MOVE"]
    card_w = max(18, (width - 4) // 3)
    cards = [service_card(snapshot.services.get(n, ServiceStatus(n)), card_w, pal) for n in names]
    lines.append(pal.bold("Runtime map"))
    for row in range(0, len(cards), 3):
        group = cards[row : row + 3]
        for sub in range(2):
            lines.append("  ".join(fit(card[sub], card_w) for card in group))
        lines.append("")

    blockers = list(snapshot.blockers.values())[-12:]
    expected = [(c, d, t) for c, d, t in blockers if ui.profile == "pc-test" and is_pc_expected(d)]
    real = [(c, d, t) for c, d, t in blockers if not (ui.profile == "pc-test" and is_pc_expected(d))]

    lines.append(pal.bold("Needs attention"))
    if real:
        for chan, desc, t in real[-5:]:
            lines.append(f" {pal.dim(t)} {pal.level('WARN'):<9} {chan:<7} {desc}")
    else:
        lines.append(" no non-PC blockers detected")
    lines.append("")
    lines.append(pal.bold("Expected missing on PC"))
    if expected:
        for chan, desc, t in expected[-5:]:
            lines.append(f" {pal.dim(t)} {chan:<7} {desc}")
    else:
        lines.append(" none detected")

    lines.append("")
    lines.append(pal.bold("Signal pressure"))
    top = snapshot.endpoints.most_common(5)
    max_count = top[0][1] if top else 1
    if top:
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
            lines.append(f" {ep:<30} {kind:<6} {hbar(count, max_count, 14, pal)} {count}")
    else:
        lines.append(" waiting for endpoint activity")
    return lines[:height]


def render_right(
    width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette, ascii_mode: bool
) -> list[str]:
    lines: list[str] = []
    errs, warns, oks, pc_count = health_summary_for(snapshot, ui)
    ev = selected_event(snapshot, ui)
    lines.append(pal.bold("Runtime"))
    lines.append(f"profile      {'PC TEST' if ui.profile == 'pc-test' else 'ROBOT'}")
    lines.append(
        f"health       {pal.red(str(errs)+' err') if errs else pal.green('no err')}  {pal.cyan(str(pc_count)+' pc') if pc_count else pal.green('no pc')}  {pal.yellow(str(warns)+' warn') if warns else pal.green('no warn')}"
    )
    lines.append(f"events       {len(snapshot.events)}")
    lines.append(f"hidden noise {snapshot.hidden_noise}")
    lines.append("")
    lines.append(pal.bold("Selected event"))
    if ev is not None:
        lines.append(f"time         {ev.time}")
        lines.append(f"level        {ev.level.upper().replace('WARNING','WARN')}")
        lines.append(f"channel      {ev.channel}")
        lines.append(f"source       {crop(ev.source, max(8, width - 14))}")
        lines.append("message")
        msg = clean_path(ev.message)
        chunk = max(12, width - 4)
        for i in range(0, min(len(msg), chunk * 5), chunk):
            lines.append("  " + crop(msg[i : i + chunk], chunk))
    else:
        lines.append("no event selected")
    lines.append("")
    lines.append(pal.bold("Suggested fix"))
    for item in suggested_fix(ev, ui)[:7]:
        lines.append("- " + crop(item, max(8, width - 4)))
    lines.append("")
    if 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Companion":
        lines.append(pal.bold("Companion quick view"))
        goal = getattr(snapshot, "companion_goal", {}) or {}
        needs = getattr(snapshot, "companion_needs", {}) or {}
        lines.append(
            f"need        {crop(str(needs.get('dominant_need', goal.get('dominant_need', '-'))), max(8, width - 14))}"
        )
        lines.append(
            f"goal        {crop(str(goal.get('behavior', needs.get('recommended_goal', '-'))), max(8, width - 14))}"
        )
        lines.append(f"priority    {crop(str(goal.get('priority', '-')), max(8, width - 14))}")
        lines.append(f"actions     {len(goal.get('actions') or [])}")
        execution = getattr(snapshot, "companion_execution", {}) or {}
        lines.append(f"execution   {crop(str(execution.get('reason', '-')), max(8, width - 14))}")
        auto = getattr(snapshot, "companion_auto", {}) or {}
        decision = auto.get("last_decision") if isinstance(auto.get("last_decision"), dict) else auto
        lines.append(f"auto_gate   {crop(str(decision.get('reason', '-')), max(8, width - 14))}")
        lines.append(f"probe       {crop(snapshot.companion_probe_error or 'ok', max(8, width - 14))}")
        lines.append("")
    if 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Expression":
        lines.append(pal.bold("Expression quick view"))
        core = _expression_core(snapshot)
        st = core["state"]
        lines.append(f"emotion     {crop(str(st.get('emotion', '-')), max(8, width - 14))}")
        lines.append(f"attention   {crop(str(st.get('attention', '-')), max(8, width - 14))}")
        lines.append(f"arousal     {crop(str(st.get('arousal', '-')), max(8, width - 14))}")
        lines.append(f"reason      {crop(str(st.get('reason', '-')), max(8, width - 14))}")
        lines.append(f"probe       {crop(snapshot.expression_probe_error or 'ok', max(8, width - 14))}")
        lines.append("")
        output_plan = getattr(snapshot, "expression_output_plan", {}) or {}
        if isinstance(output_plan, dict) and output_plan:
            lines.append(pal.bold("Output quick view"))
            lines.append(f"enabled     {output_plan.get('enabled', '-')}")
            lines.append(f"dry_run     {output_plan.get('dry_run_default', '-')}")
            lines.append(f"actions     {output_plan.get('action_count', '-')}")
            lines.append("")
    if 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Camera":
        lines.append(pal.bold("Camera quick view"))
        status = snapshot.camera_status or {}
        cap = status.get("capture") if isinstance(status.get("capture"), dict) else {}
        imx = status.get("imx500") if isinstance(status.get("imx500"), dict) else {}
        lines.append(f"camera       {'live' if status.get('live') else 'not live'}")
        lines.append(f"backend      {crop(str(cap.get('backend', '-')), max(8, width - 14))}")
        lines.append(f"imx500       {crop(str(imx.get('reason', '-')), max(8, width - 14))}")
        lines.append(f"probe        {crop(snapshot.camera_probe_error or 'ok', max(8, width - 14))}")
        lines.append("")
    lines.append(pal.bold("Top endpoints"))
    for ep, count in snapshot.endpoints.most_common(4):
        lines.append(f"{crop(ep, max(8, width - 8)):<{max(8, width - 8)}} {count}")
    return box("INSPECTOR", lines, width, height, pal, ascii_mode)
