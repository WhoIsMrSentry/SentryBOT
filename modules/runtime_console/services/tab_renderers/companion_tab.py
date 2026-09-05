from __future__ import annotations

from typing import Any

from ..models import (
    Palette,
    Snapshot,
    UIState,
    crop,
)
from ..robot_process import _gateway_base_url
from .overview_tab import _score_bar


def _yn(v: object) -> str:
    if isinstance(v, bool):
        return "Y" if v else "N"
    return str(v)


def _reason_line(d: dict, width: int, key: str = "reason") -> str:
    if not isinstance(d, dict):
        return "-"
    return crop(str(d.get(key, "-")), max(8, width - 38))


def _header_lines(snapshot: Snapshot, pal: Palette, width: int) -> list[str]:
    lines = [pal.bold("Companion needs / goal / loop / execution")]
    probe = (
        "ok"
        if not snapshot.companion_probe_error
        else crop(snapshot.companion_probe_error, max(10, width - 10))
    )
    lines.append(f"probe={probe}  gateway={snapshot.companion_probe_url or _gateway_base_url()}")
    return lines


def _need_goal_lines(needs: dict, goal: dict, pal: Palette, width: int) -> list[str]:
    dominant = needs.get("dominant_need", goal.get("dominant_need", "-"))
    recommended = needs.get("recommended_goal", goal.get("recommended_goal", "-"))
    behavior = goal.get("behavior", recommended)
    priority = goal.get("priority", "-")
    idle_s = needs.get("idle_s", "-")
    owner_present = needs.get("owner_present", goal.get("owner_present", "-"))

    lines = ["", pal.bold("Need / goal")]
    lines.append(f" need={crop(str(dominant), 14):<14} goal={crop(str(recommended), max(8, width - 30))}")
    lines.append(
        f" behavior={crop(str(behavior), max(8, width - 34))} prio={priority} idle={idle_s} owner={_yn(owner_present)}"
    )
    lines.append(
        f" safe={_yn(goal.get('safe_to_execute', '-'))} auto={_yn(goal.get('auto_execute', '-'))}"
        f" expr={crop(str(goal.get('expression_event', '-')), max(8, width - 30))}"
    )
    return lines


def _memory_decision_lines(memory_shadow: dict, memory_bias: dict, pal: Palette, width: int) -> list[str]:
    lines = [pal.bold("Memory decision")]
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
    return lines


def _behavior_loop_lines(loop: dict, loop_decision: Any, pal: Palette, width: int) -> list[str]:
    lines = [pal.bold("Behavior loop")]
    if loop:
        lines.append(
            f" enabled={_yn(loop.get('enabled', '-'))} interval={loop.get('interval_s', '-')}s"
            f" min_idle={loop.get('min_idle_s', '-')}s dry={_yn(loop.get('dry_run', '-'))}"
        )
        lines.append(
            f" decision={_reason_line(loop_decision, width)}"
            f" tick={_yn(loop_decision.get('should_tick', '-'))} exec={_yn(loop_decision.get('executed', '-'))}"
        )
    else:
        lines.append(" no behavior loop probe yet; use r or :looptick")
    return lines


def _loop_history_lines(loop_history: list, height: int, len_lines: int, width: int) -> list[str]:
    lines = ["", "Recent behavior loop"]
    if loop_history:
        max_hist = max(1, min(3, max(1, height - len_lines - 12)))
        for idx, item in enumerate(loop_history[:max_hist], 1):
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or item.get("execution_reason") or "-")
            plan = str(item.get("plan_id") or item.get("behavior") or "-")
            ex = _yn(item.get("executed") if "executed" in item else item.get("available", "-"))
            lines.append(f" {idx:02d}. {crop(reason, 16):<16} exec={ex:<3} {crop(plan, max(8, width - 36))}")
    else:
        lines.append(" no history yet; use :looptick")
    return lines


def _auto_gate_lines(auto: dict, auto_decision: Any, pal: Palette, width: int) -> list[str]:
    lines = [pal.bold("Auto-execute gate")]
    if auto:
        lines.append(
            f" enabled={_yn(auto.get('enabled', '-'))}"
            f" dry={_yn(auto.get('dry_run_default', auto.get('dry_run', '-')))}"
            f" real_hw={_yn(auto.get('allow_real_hardware', '-'))}"
        )
        lines.append(
            f" decision={_reason_line(auto_decision, width)}"
            f" run={_yn(auto_decision.get('should_execute', '-'))}"
            f" exec={_yn(auto_decision.get('executed', '-'))}"
        )
    else:
        lines.append(" no auto gate probe yet; use r")
    return lines


def _execution_lines(execution: dict, steps: list, pal: Palette, width: int) -> list[str]:
    lines = ["", pal.bold("Execution dry-run")]
    if not execution:
        lines.append(" no execution probe yet; use :execute")
        return lines
    lines.append(
        f" enabled={_yn(execution.get('enabled', '-'))}"
        f" dry={_yn(execution.get('dry_run', execution.get('dry_run_default', '-')))}"
        f" applied={_yn(execution.get('applied', '-'))}"
    )
    lines.append(
        f" available={_yn(execution.get('available', '-'))}"
        f" reason={crop(str(execution.get('reason', '-')), max(8, width - 32))}"
        f" steps={execution.get('step_count', len(steps))}"
    )
    for idx, step in enumerate(steps[:2], 1):
        if not isinstance(step, dict):
            continue
        component = str(step.get("component") or "-")
        url = str(step.get("url") or "-")
        risk = str(step.get("risk") or "-")
        lines.append(f" {idx:02d}. {component:<10} {crop(url, max(8, width - 32))} risk={risk}")
    return lines


def _action_plan_lines(actions: list, height: int, len_lines: int, pal: Palette, width: int) -> list[str]:
    if height - len_lines <= 5:
        return []
    lines = ["", pal.bold("Safe action plan")]
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
    return lines


_SCORE_ORDER = [
    "social",
    "curiosity",
    "boredom",
    "energy",
    "rest",
    "safety",
    "owner_proximity",
    "exploration",
]


def _score_lines(scores: Any, height: int, len_lines: int, pal: Palette, width: int) -> list[str]:
    if height - len_lines <= 4:
        return []
    lines = ["", pal.bold("Need scores")]
    if isinstance(scores, dict) and scores:
        remaining = max(0, height - len(lines))
        for key in _SCORE_ORDER[:remaining]:
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
    return lines


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

    lines: list[str] = []
    lines.extend(_header_lines(snapshot, pal, width))
    lines.extend(_need_goal_lines(needs, goal, pal, width))
    lines.extend(_memory_decision_lines(memory_shadow, memory_bias, pal, width))
    lines.extend(_behavior_loop_lines(loop, loop_decision, pal, width))

    history = _loop_history_lines(loop_history, height, len(lines), width)
    lines.extend(history)

    world = _world_memory_block(memory, mem_counts, mem_recent, autowrite, aw_items, pal, width)
    lines.extend(world)

    lines.extend(_auto_gate_lines(auto, auto_decision, pal, width))
    lines.extend(_execution_lines(execution, steps, pal, width))
    lines.extend(_action_plan_lines(actions, height, len(lines), pal, width))
    lines.extend(_score_lines(scores, height, len(lines), pal, width))
    return lines[:height]


def _world_memory_block(
    memory: dict,
    mem_counts: dict,
    mem_recent: list,
    autowrite: dict,
    aw_items: list,
    pal: Palette,
    width: int,
) -> list[str]:
    lines = [pal.bold("World memory")]
    if not memory:
        lines.append(" no world-memory probe yet; use r or :memory")
        return lines
    try:
        total = int(memory.get("total", 0) or 0)
    except Exception:
        total = 0
    lines.append(
        f" total={total} people={mem_counts.get('people', 0)} objects={mem_counts.get('objects', 0)}"
        f" events={mem_counts.get('events', 0)} obs={mem_counts.get('observations', 0)}"
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
    return lines
