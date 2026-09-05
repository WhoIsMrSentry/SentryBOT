from __future__ import annotations

from ..models import (
    Palette,
    Snapshot,
    UIState,
    crop,
    dict_get,
    render_kv,
)
from ..robot_process import _expression_core, _gateway_base_url


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
