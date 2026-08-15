from __future__ import annotations

import shutil
from typing import Any

from .models import (
    APP,
    TABS,
    VERSION,
    LogEvent,
    Palette,
    ServiceStatus,
    Snapshot,
    UIState,
    box,
    clean_path,
    command_prompt,
    crop,
    dict_get,
    event_line,
    fit,
    hbar,
    health_summary_for,
    is_pc_expected,
    list_config_files,
    newest_first_events,
    preview_file,
    render_kv,
    safe_text,
    selected_event,
    service_card,
    service_is_pc_expected,
    suggested_fix,
    tab_strip,
    visible_len,
)
from .robot_process import _expression_core, _gateway_base_url


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


def render_camera(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    status = snapshot.camera_status or {}
    onsensor = snapshot.camera_onsensor or {}
    capture = status.get("capture") if isinstance(status.get("capture"), dict) else {}
    imx = status.get("imx500") if isinstance(status.get("imx500"), dict) else {}
    bus = status.get("onsensor") if isinstance(status.get("onsensor"), dict) else {}
    latest_snapshot = onsensor.get("snapshot") if isinstance(onsensor.get("snapshot"), dict) else None
    lines: list[str] = []
    lines.append(pal.bold("Camera / IMX500 status"))
    lines.append(f"gateway: {snapshot.camera_probe_url or _gateway_base_url()}")
    if snapshot.camera_probe_error and not status:
        lines.append(pal.yellow("probe: " + crop(snapshot.camera_probe_error, max(10, width - 8))))
        lines.append("attach mode needs an already running gateway")
    else:
        lines.append(
            "probe: "
            + (
                pal.green("ok")
                if not snapshot.camera_probe_error
                else pal.yellow(snapshot.camera_probe_error)
            )
        )
    lines.append("")
    lines.append(pal.bold("Capture"))
    render_kv(lines, "enabled/live", f"{bool(status.get('enabled'))}/{bool(status.get('live'))}", width)
    render_kv(lines, "backend", capture.get("backend"), width)
    render_kv(lines, "source", capture.get("source"), width)
    render_kv(lines, "running/frame", f"{capture.get('running')}/{capture.get('has_frame')}", width)
    render_kv(lines, "opencv", dict_get(capture, "opencv", "available"), width)
    render_kv(lines, "picamera2", dict_get(capture, "picamera2", "available"), width)
    lines.append("")
    lines.append(pal.bold("IMX500"))
    render_kv(lines, "enabled/available", f"{imx.get('enabled')}/{imx.get('available')}", width)
    render_kv(lines, "running", imx.get("running"), width)
    render_kv(lines, "reason", imx.get("reason"), width)
    render_kv(lines, "model/labels", f"{imx.get('model_path_exists')}/{imx.get('labels_path_exists')}", width)
    render_kv(lines, "last_publish_age_s", imx.get("last_publish_age_s"), width)
    lines.append("")
    lines.append(pal.bold("On-sensor bus"))
    render_kv(lines, "attached/latest", f"{bus.get('attached')}/{bus.get('has_latest')}", width)
    render_kv(lines, "published/subs", f"{bus.get('published_count')}/{bus.get('subscribers')}", width)
    render_kv(lines, "latest_age_s", bus.get("latest_age_s"), width)
    if latest_snapshot:
        dets = latest_snapshot.get("detections") or []
        lines.append(pal.bold(f"Latest detections: {len(dets)}"))
        for det in dets[: max(0, height - len(lines) - 1)]:
            if not isinstance(det, dict):
                continue
            label = det.get("label", "object")
            score = det.get("score", 0)
            lines.append(f" - {label:<16} {score}")
    else:
        lines.append("no on-sensor snapshot yet")
    if height > 26:
        picam_err = dict_get(capture, "picamera2", "import_error")
        if picam_err:
            lines.append("")
            render_kv(lines, "picamera2_error", picam_err, width)
        if imx.get("model_path"):
            render_kv(lines, "model_path", imx.get("model_path"), width)
    return lines[:height]


def render_expression(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    core = _expression_core(snapshot)
    st = core["state"]
    targets = core["targets"]
    history = (
        snapshot.expression_history.get("history")
        if isinstance(snapshot.expression_history, dict)
        else []
    )
    event_counts = core["payload"].get("event_counts") if isinstance(core["payload"], dict) else {}
    lines: list[str] = []
    lines.append(pal.bold("Semantic expression state"))
    lines.append(f"gateway: {snapshot.expression_probe_url or _gateway_base_url()}")
    if snapshot.expression_probe_error and not st:
        lines.append(pal.yellow("probe: " + crop(snapshot.expression_probe_error, max(10, width - 8))))
        lines.append("Expression module is not mounted or gateway is still starting.")
        lines.append("")
    else:
        lines.append(
            "probe: "
            + (
                pal.green("ok")
                if not snapshot.expression_probe_error
                else pal.yellow(snapshot.expression_probe_error)
            )
        )
    lines.append("")
    lines.append(pal.bold("Current state"))
    render_kv(lines, "emotion", st.get("emotion"), width)
    render_kv(lines, "arousal", st.get("arousal"), width)
    render_kv(lines, "attention", st.get("attention"), width)
    render_kv(lines, "energy", st.get("energy"), width)
    render_kv(lines, "speaking", st.get("speaking"), width)
    render_kv(lines, "listening", st.get("listening"), width)
    render_kv(lines, "confidence", st.get("confidence"), width)
    render_kv(lines, "source", st.get("source"), width)
    render_kv(lines, "reason", st.get("reason"), width)
    lines.append("")
    lines.append(pal.bold("Derived hardware targets"))
    led = targets.get("led") if isinstance(targets.get("led"), dict) else {}
    oled = targets.get("oled") if isinstance(targets.get("oled"), dict) else {}
    pose = targets.get("pose") if isinstance(targets.get("pose"), dict) else {}
    speech = targets.get("speech") if isinstance(targets.get("speech"), dict) else {}
    render_kv(lines, "led", f"{led.get('mode', '-')} {led.get('color', '-')}", width)
    render_kv(lines, "oled", f"{oled.get('mood', '-')} attention={oled.get('attention', '-')}", width)
    render_kv(lines, "pose", f"ear={pose.get('ear_gesture', '-')} energy={pose.get('energy', '-')}", width)
    render_kv(lines, "speech", f"tone={speech.get('tone', '-')} arousal={speech.get('arousal', '-')}", width)
    output_plan = getattr(snapshot, "expression_output_plan", {}) or {}
    output_status = getattr(snapshot, "expression_output_status", {}) or {}
    output_err = getattr(snapshot, "expression_output_probe_error", "") or ""
    if isinstance(output_plan, dict) or isinstance(output_status, dict):
        lines.append("")
        lines.append(pal.bold("Expression output bridge"))
        if output_err and not output_plan:
            lines.append(pal.yellow("probe: " + crop(output_err, max(10, width - 8))))
        else:
            lines.append("probe: " + (pal.green("ok") if not output_err else pal.yellow(output_err)))
        enabled = (
            output_plan.get("enabled", output_status.get("enabled", "-"))
            if isinstance(output_plan, dict)
            else "-"
        )
        dry = (
            output_plan.get("dry_run_default", output_status.get("dry_run_default", "-"))
            if isinstance(output_plan, dict)
            else "-"
        )
        render_kv(lines, "enabled/dry", f"{enabled}/{dry}", width)
        render_kv(
            lines,
            "actions",
            output_plan.get("action_count", "-") if isinstance(output_plan, dict) else "-",
            width,
        )
        actions = output_plan.get("actions", []) if isinstance(output_plan, dict) else []
        if isinstance(actions, list) and actions:
            for action in actions[:3]:
                if not isinstance(action, dict):
                    continue
                comp = str(action.get("component") or "-")
                url = str(action.get("url") or "-")
                note = str(action.get("note") or "")
                lines.append(" " + crop(f"{comp:<10} {url} {note}", max(10, width - 2)))
        last_apply = output_status.get("last_apply") if isinstance(output_status, dict) else None
        if isinstance(last_apply, dict):
            render_kv(
                lines,
                "last_apply",
                f"applied={last_apply.get('applied')} reason={last_apply.get('reason', '-')}",
                width,
            )
    if isinstance(event_counts, dict) and event_counts:
        lines.append("")
        lines.append(pal.bold("Top expression events"))
        for key, val in sorted(event_counts.items(), key=lambda kv: str(kv[1]), reverse=True)[:5]:
            lines.append(f" {crop(str(key), 28):<28} {val}")
    lines.append("")
    lines.append(pal.bold("History"))
    if not history:
        lines.append(" no expression state transitions yet")
    else:
        for rec in list(history)[-max(1, min(8, height - len(lines) - 1)):][::-1]:
            if not isinstance(rec, dict):
                continue
            nxt = rec.get("next") if isinstance(rec.get("next"), dict) else {}
            at = str(rec.get("at") or nxt.get("updated_at") or "-")
            at = at[11:19] if len(at) >= 19 else at
            msg = f"{nxt.get('emotion','-')} / {nxt.get('attention','-')} / {nxt.get('reason','-')}"
            lines.append(f" {at} {crop(msg, max(10, width - 12))}")
    return lines[:height]


def render_companion(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    needs = getattr(snapshot, "companion_needs", {}) or {}
    goal = getattr(snapshot, "companion_goal", {}) or {}
    execution = getattr(snapshot, "companion_execution", {}) or {}
    auto = getattr(snapshot, "companion_auto", {}) or {}
    loop = getattr(snapshot, "companion_goal", {}) or {}
    scores = (
        needs.get("scores")
        if isinstance(needs.get("scores"), dict)
        else goal.get("scores")
        if isinstance(goal.get("scores"), dict)
        else {}
    )
    actions = goal.get("actions") if isinstance(goal.get("actions"), list) else []
    steps = execution.get("steps") if isinstance(execution.get("steps"), list) else []
    auto_decision = auto.get("last_decision") if isinstance(auto.get("last_decision"), dict) else auto
    loop_decision = loop.get("last_decision") if isinstance(loop.get("last_decision"), dict) else loop
    loop_history = loop.get("history") if isinstance(loop.get("history"), list) else []
    memory = getattr(snapshot, "world_memory", {}) or {}
    autowrite = getattr(snapshot, "world_memory_autowrite", {}) or {}
    mem_counts = memory.get("counts") if isinstance(memory.get("counts"), dict) else {}
    mem_recent = memory.get("recent") if isinstance(memory.get("recent"), list) else []
    aw_items = autowrite.get("items") if isinstance(autowrite.get("items"), list) else []
    memory_shadow = getattr(snapshot, "memory_shadow", {}) or {}
    memory_bias = getattr(snapshot, "memory_needs_bias", {}) or {}

    def yn(v: object) -> str:
        if isinstance(v, bool):
            return "Y" if v else "N"
        return str(v)

    def reason_line(d: dict, key: str = "reason") -> str:
        if not isinstance(d, dict):
            return "-"
        return crop(str(d.get(key, "-")), max(8, width - 38))

    lines: list[str] = []
    lines.append(pal.bold("Companion needs / goal / loop / execution"))
    probe = (
        "ok"
        if not snapshot.companion_probe_error
        else crop(snapshot.companion_probe_error, max(10, width - 10))
    )
    lines.append(f"probe={probe}  gateway={snapshot.companion_probe_url or _gateway_base_url()}")

    dominant = needs.get("dominant_need", goal.get("dominant_need", "-"))
    recommended = needs.get("recommended_goal", goal.get("recommended_goal", "-"))
    behavior = goal.get("behavior", recommended)
    priority = goal.get("priority", "-")
    idle_s = needs.get("idle_s", "-")
    owner_present = needs.get("owner_present", goal.get("owner_present", "-"))

    lines.append("")
    lines.append(pal.bold("Need / goal"))
    lines.append(f" need={crop(str(dominant), 14):<14} goal={crop(str(recommended), max(8, width - 30))}")
    lines.append(
        f" behavior={crop(str(behavior), max(8, width - 34))} prio={priority} idle={idle_s} owner={yn(owner_present)}"
    )
    lines.append(
        f" safe={yn(goal.get('safe_to_execute', '-'))} auto={yn(goal.get('auto_execute', '-'))} expr={crop(str(goal.get('expression_event', '-')), max(8, width - 30))}"
    )

    lines.append("")
    lines.append(pal.bold("Memory decision"))
    if memory_shadow:
        shadow_need = memory_shadow.get("recommended_need", "-")
        shadow_goal = memory_shadow.get("recommended_goal", "-")
        shadow_mode = memory_shadow.get("mode", "-")
        shadow_apply = memory_shadow.get("apply_to_needs", False)
        shadow_conf = memory_shadow.get("confidence", 0)
        try:
            shadow_conf_s = f"{float(shadow_conf):.2f}"
        except Exception:
            shadow_conf_s = str(shadow_conf)
        lines.append(f" shadow={shadow_need}/{crop(str(shadow_goal), max(8, width - 28))}")
        lines.append(f" mode={shadow_mode} apply={shadow_apply} conf={shadow_conf_s}")
    else:
        lines.append(" shadow=-")
    if memory_bias:
        bias_need = memory_bias.get("result_need") or memory_bias.get("memory_need") or "-"
        bias_goal = memory_bias.get("result_goal") or memory_bias.get("memory_goal") or "-"
        applied = memory_bias.get("applied", False)
        reason = memory_bias.get("reason", "-")
        boost = memory_bias.get("boost", "-")
        lines.append(f" bias={bias_need}/{crop(str(bias_goal), max(8, width - 26))}")
        lines.append(
            f" applied={applied} boost={boost} reason={crop(str(reason), max(8, width - 31))}"
        )
    else:
        lines.append(" bias=-")

    lines.append(pal.bold("Behavior loop"))
    if loop:
        lines.append(
            f" enabled={yn(loop.get('enabled', '-'))} interval={loop.get('interval_s', '-')}s min_idle={loop.get('min_idle_s', '-')}s dry={yn(loop.get('dry_run', '-'))}"
        )
        lines.append(
            f" decision={reason_line(loop_decision)} tick={yn(loop_decision.get('should_tick', '-'))} exec={yn(loop_decision.get('executed', '-'))}"
        )
    else:
        lines.append(" no behavior loop probe yet; use r or :looptick")

    lines.append("")
    lines.append(pal.bold("Recent behavior loop"))
    if loop_history:
        max_hist = max(1, min(3, max(1, height - len(lines) - 12)))
        for idx, item in enumerate(loop_history[:max_hist], 1):
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or item.get("execution_reason") or "-")
            plan = str(item.get("plan_id") or item.get("behavior") or "-")
            ex = yn(item.get("executed") if "executed" in item else item.get("available", "-"))
            lines.append(f" {idx:02d}. {crop(reason, 16):<16} exec={ex:<3} {crop(plan, max(8, width - 36))}")
    else:
        lines.append(" no history yet; use :looptick")

    lines.append("")
    lines.append(pal.bold("World memory"))
    if memory:
        try:
            total = int(memory.get("total", 0) or 0)
        except Exception:
            total = 0
        lines.append(
            f" total={total} people={mem_counts.get('people', 0)} objects={mem_counts.get('objects', 0)} events={mem_counts.get('events', 0)} obs={mem_counts.get('observations', 0)}"
        )
        if mem_recent:
            item = mem_recent[0] if isinstance(mem_recent[0], dict) else {}
            label = f"{item.get('kind', '-')}/{item.get('name', '-')}"
            src = item.get("source", "-")
            cnt = item.get("count", "-")
            lines.append(f" latest={crop(str(label), max(8, width - 34))} src={src} x{cnt}")
        else:
            lines.append(" latest=-")
        if autowrite:
            aw_src = autowrite.get("source_type", "-")
            aw_count = autowrite.get("count", 0)
            aw_created = autowrite.get("created_count", 0)
            if aw_items:
                aw_item = aw_items[0] if isinstance(aw_items[0], dict) else {}
                aw_label = f"{aw_item.get('kind', '-')}/{aw_item.get('name', '-')}"
                lines.append(
                    f" autowrite={aw_src} count={aw_count} created={aw_created} {crop(str(aw_label), max(8, width - 46))}"
                )
            else:
                lines.append(f" autowrite={aw_src} count={aw_count} created={aw_created}")
    else:
        lines.append(" no world-memory probe yet; use r or :memory")

    lines.append(pal.bold("Auto-execute gate"))
    if auto:
        lines.append(
            f" enabled={yn(auto.get('enabled', '-'))} dry={yn(auto.get('dry_run_default', auto.get('dry_run', '-')))} real_hw={yn(auto.get('allow_real_hardware', '-'))}"
        )
        lines.append(
            f" decision={reason_line(auto_decision)} run={yn(auto_decision.get('should_execute', '-'))} exec={yn(auto_decision.get('executed', '-'))}"
        )
    else:
        lines.append(" no auto gate probe yet; use r")

    lines.append("")
    lines.append(pal.bold("Execution dry-run"))
    if execution:
        lines.append(
            f" enabled={yn(execution.get('enabled', '-'))} dry={yn(execution.get('dry_run', execution.get('dry_run_default', '-')))} applied={yn(execution.get('applied', '-'))}"
        )
        lines.append(
            f" available={yn(execution.get('available', '-'))} reason={crop(str(execution.get('reason', '-')), max(8, width - 32))} steps={execution.get('step_count', len(steps))}"
        )
        for idx, step in enumerate(steps[:2], 1):
            if not isinstance(step, dict):
                continue
            component = str(step.get("component") or "-")
            url = str(step.get("url") or "-")
            risk = str(step.get("risk") or "-")
            lines.append(f" {idx:02d}. {component:<10} {crop(url, max(8, width - 32))} risk={risk}")
    else:
        lines.append(" no execution probe yet; use :execute")

    if height - len(lines) > 5:
        lines.append("")
        lines.append(pal.bold("Safe action plan"))
        if actions:
            for idx, action in enumerate(actions[:2], 1):
                if not isinstance(action, dict):
                    continue
                typ = str(action.get("type") or "-")
                label = str(
                    action.get("event")
                    or action.get("name")
                    or action.get("label")
                    or action.get("mode")
                    or "-"
                )
                risk = str(action.get("risk") or "-")
                lines.append(f" {idx:02d}. {typ:<10} {crop(label, max(8, width - 30))} risk={risk}")
        else:
            lines.append(" no action plan yet")

    if height - len(lines) > 4:
        lines.append("")
        lines.append(pal.bold("Need scores"))
        if isinstance(scores, dict) and scores:
            order = [
                "social",
                "curiosity",
                "boredom",
                "energy",
                "rest",
                "safety",
                "owner_proximity",
                "exploration",
            ]
            remaining = max(0, height - len(lines))
            for key in order[:remaining]:
                if key in scores:
                    try:
                        val = float(scores.get(key) or 0.0)
                        val_s = f"{val:5.1f}"
                    except Exception:
                        val_s = str(scores.get(key))
                    bar = _score_bar(scores.get(key), width=max(6, min(16, width - 24)))
                    lines.append(f" {key:<16} {val_s:>6} {bar}")
        else:
            lines.append(" no scores yet")
    return lines[:height]


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


def render_config(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    files = list_config_files(ui.root)
    left_w = min(38, max(24, width // 3))
    right_w = width - left_w - 3
    selected = min(max(0, ui.selected_config), max(0, len(files) - 1))
    ui.selected_config = selected
    left: list[str] = [pal.dim("YAML files  (Up/Down select, e edit)")]
    for idx, path in enumerate(files[: max(1, height - 2)]):
        rel = str(path.relative_to(ui.root)).replace("\\", "/")
        line = f"{idx+1:>2} {rel}"
        left.append(pal.cyan(line) if idx == selected else line)
    if not files:
        left.append("no yaml config files found")
    right: list[str] = []
    if files:
        rel = str(files[selected].relative_to(ui.root)).replace("\\", "/")
        right.append(pal.bold(rel))
        right.append(pal.dim("edit: press e, enter dotted.key, enter value"))
        right.append("")
        for i, line in enumerate(preview_file(files[selected], max(0, height - 4)), 1):
            right.append(f"{i:>3} {line}")
    rows = []
    for i in range(height):
        l = fit(left[i] if i < len(left) else "", left_w)
        r = fit(right[i] if i < len(right) else "", right_w)
        rows.append(l + pal.dim(" | ") + r)
    return rows


def render_search(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines = [
        pal.dim(
            f"query: {ui.project_search or '<none>'}  results:{len(ui.project_results)}  press s to search"
        )
    ]
    lines.append("")
    for res in ui.project_results[: max(0, height - 2)]:
        lines.append(f"{pal.cyan(res.path)}:{res.line}  {res.text}")
    if not ui.project_results and not ui.project_search:
        lines.append("Try: s  piper / vosk / vlm / auth_token / arduino")
    return lines[:height]


def render_actions(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines = [
        pal.bold("Command workspace"),
        "This screen is intentionally safe for PC testing; it does not assume robot hardware is attached.",
        "",
        pal.bold("Command palette"),
        " :profile pc              classify hardware warnings as expected PC-test gaps",
        " :profile robot           classify hardware warnings as real robot blockers",
        " :filter <text>           filter Logs tab",
        " :view human|full|warn    change Logs view mode",
        " :search <text>           project-wide search",
        " :set <key> <value>       edit selected YAML key from Config tab",
        " :camera refresh          probe /camera/status now",
        " :expression refresh      probe /expression/state now",
        " :expression output       view dry-run output plan",
        " :tab camera             open Camera / IMX500 panel",
        " :quit                    exit TUI",
        "",
        pal.bold("Next engineering phases"),
        " 08 vision request gate: stop unnecessary VLM calls and label true inference vs polls",
        " 09 persistent TTS worker: load Piper once and prevent test-tone-success speech",
        " 10 semantic expression engine: one source for LED/OLED/emotion/motion state",
    ]
    return lines[:height]


def render_help(width: int, height: int, pal: Palette) -> list[str]:
    lines = [
        pal.bold("Navigation"),
        " 1-9             switch workspace tab",
        " Up/Down         move log selection or config file selection",
        " PageUp/PageDn   scroll log viewport",
        " /               filter logs",
        " v               cycle log view: human/full/warn",
        " s               search project files",
        " e               edit selected YAML key in Config",
        " :               command palette",
        " c               clear filter/search/message",
        " r               refresh immediately",
        " q               quit",
        "",
        pal.bold("Layout"),
        " Navigator: sections and health",
        " Workspace: selected tool view",
        " Inspector: selected log/config/event details and suggested fix",
        " Command bar: input and active shortcut state",
        "",
        pal.bold("Logs"),
        " Raw stdout: logs/tui.log",
        " Detailed runtime log: logs/sentry.log",
        " TUI hides polling spam from Overview and groups it in Signals.",
        " Camera tab: live /camera/status and /camera/onsensor/latest diagnostics",
        " Expression tab: live semantic state, targets, event history",
        " Companion tab: needs + semantic goal selector",
        " :execute dry-run current companion goal",
        " :autotick dry-run auto gate tick",
        " :looptick dry-run behavior loop tick",
        " :memory refresh world-memory panel",
        " :memorybias refresh memory shadow/bias",
    ]
    return lines[:height]


def render_main(
    width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette, ascii_mode: bool
) -> list[str]:
    tab_name = TABS[ui.active_tab] if 0 <= ui.active_tab < len(TABS) else "Overview"
    inner_h = height - 2
    if tab_name == "Overview":
        content = render_overview(width, inner_h, snapshot, ui, pal, ascii_mode)
    elif tab_name == "Logs":
        content = render_logs(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Signals":
        content = render_signals(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Config":
        content = render_config(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Search":
        content = render_search(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Actions":
        content = render_actions(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Companion":
        content = render_companion(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Expression":
        content = render_expression(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Camera":
        content = render_camera(width, inner_h, snapshot, ui, pal)
    else:
        content = render_help(width, inner_h, pal)
    return box(
        "WORKSPACE / " + tab_name.upper(),
        [tab_strip(width - 4, ui, pal), ""] + content,
        width,
        height,
        pal,
        ascii_mode,
    )


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


def render_screen(
    snapshot: Snapshot,
    ui: UIState,
    robot_status: str,
    colors: bool = True,
    ascii_mode: bool = False,
) -> str:
    pal = Palette(colors)
    size = shutil.get_terminal_size((132, 38))
    width = max(96, size.columns)
    height = max(26, size.lines)
    header_h = 2
    footer_h = 3
    body_h = height - header_h - footer_h
    side_w = 26
    right_w = 38 if width >= 126 else 0
    gap = 1
    main_w = width - side_w - right_w - (gap * (2 if right_w else 1))
    out: list[str] = [draw_header(width, snapshot, ui, robot_status, pal)]
    breadcrumb = f" workspace={TABS[ui.active_tab].lower()}  root={crop(str(ui.root), max(10, width - 50))}"
    out.append(fit(pal.dim(breadcrumb), width))
    side = draw_sidebar(body_h, side_w, ui, snapshot, pal, ascii_mode)
    main = render_main(main_w, body_h, snapshot, ui, pal, ascii_mode)
    right = render_right(right_w, body_h, snapshot, ui, pal, ascii_mode) if right_w else []
    for i in range(body_h):
        line = side[i] + " " + main[i]
        if right_w:
            line += " " + right[i]
        out.append(fit(line, width))
    prompt = command_prompt(ui)
    status = f" tab={TABS[ui.active_tab]}  view={ui.log_view}  filter={ui.filter_text or '-'}  selected={ui.selected_event + 1} "
    out.append(fit("-" * width, width))
    out.append(fit(status, width))
    out.append(fit(prompt, width))
    return safe_text("\n".join(out))
