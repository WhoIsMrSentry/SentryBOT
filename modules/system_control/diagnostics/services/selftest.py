from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from modules.common.health import check_disk_space, check_memory
from modules.common.runtime_target import read_hardware_pressure

logger = logging.getLogger("diagnostics.selftest")

# Thread-safe cross-call stabilization state for latency and hard-heal cooldowns.
_HEAL_STATE_LOCK = threading.RLock()
_HEAL_STATE: Dict[str, Dict[str, Any]] = {}


def clear_heal_state() -> None:
    """Clear stabilization/cooldown state safely under lock."""
    with _HEAL_STATE_LOCK:
        _HEAL_STATE.clear()


def _normalize_checks(checks: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for name, raw in checks.items():
        if isinstance(raw, tuple) and len(raw) == 2:
            out[name] = {
                "enabled": True,
                "method": str(raw[0]).upper(),
                "path": str(raw[1]),
            }
            continue

        if isinstance(raw, dict):
            if not bool(raw.get("enabled", True)):
                continue
            out[name] = {
                "enabled": True,
                "method": str(raw.get("method", "GET")).upper(),
                "path": str(raw.get("path", "")),
                "timeout_ms": int(raw.get("timeout_ms", 1000)),
                "latency_warn_ms": int(raw.get("latency_warn_ms", 600)),
                "critical": bool(raw.get("critical", True)),
                "heal": raw.get("heal") if isinstance(raw.get("heal"), dict) else None,
            }
    return out


def _resolve_heal_target(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _evaluate_body_ok(path: str, resp: Any) -> bool:
    if path.endswith("/speak/status"):
        try:
            payload = resp.json()
            return bool(payload.get("ready", False))
        except Exception:
            return False
    if path.endswith("/speech/status"):
        try:
            payload = resp.json()
            return bool(payload.get("model_ready", payload.get("listening", False)))
        except Exception:
            return False
    return True


def _plan_heal(
    name: str,
    *,
    ok: bool,
    latency_only: bool,
    heal_req: Optional[Dict[str, Any]],
    heal_cfg: Dict[str, Any],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Thread-safe stabilization & cooldown decision for both soft and hard failures."""
    now = time.monotonic()
    with _HEAL_STATE_LOCK:
        if ok:
            state = _HEAL_STATE.get(name)
            if state is not None:
                state["consec"] = 0
            return False, None

        state = _HEAL_STATE.setdefault(
            name,
            {"consec": 0, "last_heal": None, "last_hard_heal": None},
        )
        if heal_req is None:
            return False, None

        if latency_only:
            state["consec"] = int(state.get("consec", 0)) + 1
            min_fails = max(1, int(heal_cfg.get("min_consecutive_latency_fails", 3)))
            cooldown_s = max(0.0, float(heal_cfg.get("latency_heal_cooldown_s", 900.0)))
            last_heal = state.get("last_heal")
            in_cooldown = last_heal is not None and (now - float(last_heal)) < cooldown_s
            if int(state.get("consec", 0)) < min_fails or in_cooldown:
                return False, {
                    "reason": "latency_stabilization",
                    "consecutive_fails": int(state.get("consec", 0)),
                    "min_required": min_fails,
                }
            state["last_heal"] = now
            state["consec"] = 0
            return True, None

        # Hard failure (5xx / invalid body / timeout / connect exception)
        hard_cooldown_s = max(0.0, float(heal_cfg.get("hard_heal_cooldown_s", 60.0)))
        last_hard = state.get("last_hard_heal")
        if hard_cooldown_s > 0 and last_hard is not None and (now - float(last_hard)) < hard_cooldown_s:
            return False, {
                "reason": "hard_heal_cooldown",
                "cooldown_s": hard_cooldown_s,
            }
        state["last_hard_heal"] = now
        state["consec"] = 0
        return True, None


def run_local_system_checks(system_cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Inspect RPi 5 / host local disk, memory, and thermal pressure."""
    cfg = system_cfg or {}
    disk_path = str(cfg.get("disk_path", ".") or ".")
    min_free_gb = float(cfg.get("min_free_gb", 0.5))
    min_free_mb = float(cfg.get("min_free_mb", 100.0))

    disk = check_disk_space(path=disk_path, min_free_gb=min_free_gb)
    pressure = read_hardware_pressure(min_free_mem_mb=min_free_mb)
    try:
        mem = check_memory(min_free_mb=min_free_mb)
    except Exception:
        mem_mb = pressure.get("mem_available_mb")
        if mem_mb is not None:
            mem = {"status": "healthy" if mem_mb >= min_free_mb else "unhealthy", "free_mb": mem_mb}
        else:
            mem = {"status": "unknown", "message": "psutil not installed"}

    disk_ok = disk.get("status") == "healthy"
    mem_ok = mem.get("status") != "unhealthy"
    thermal_ok = pressure.get("pressure_level") != "critical"
    return {
        "ok": bool(disk_ok and mem_ok and thermal_ok),
        "disk": disk,
        "memory": mem,
        "pressure": pressure,
    }


def _record_result(
    out: Dict[str, Any],
    name: str,
    entry: Dict[str, Any],
    *,
    ok: bool,
    critical: bool,
) -> None:
    out[name] = entry
    if not ok:
        if critical:
            out["failed"].append(name)
            out["ok"] = False
        else:
            out["degraded"].append(name)


def _finalize_report(
    out: Dict[str, Any],
    *,
    system_checks: Dict[str, Any] | None,
) -> Dict[str, Any]:
    if system_checks and bool(system_checks.get("enabled", True)):
        sys_report = run_local_system_checks(system_checks)
        out["system"] = sys_report
        if not sys_report.get("ok", True):
            out["degraded"].append("system")
    if not out.get("failed"):
        out["ok"] = True
    return out


def _evaluate_http_probe(
    path: str,
    resp: Any,
    latency_ms: int,
    latency_warn_ms: int,
    critical: bool,
) -> Tuple[bool, bool, Dict[str, Any]]:
    status_ok = resp.status_code == 200
    body_ok = _evaluate_body_ok(path, resp)
    latency_ok = latency_ms <= latency_warn_ms
    ok = bool(status_ok and body_ok and latency_ok)
    entry: Dict[str, Any] = {
        "ok": ok,
        "critical": critical,
        "status_code": int(resp.status_code),
        "latency_ms": latency_ms,
        "latency_warn_ms": latency_warn_ms,
        "within_latency": latency_ok,
    }
    return ok, bool(status_ok and body_ok and not latency_ok), entry


def _prepare_heal_call(
    base_url: str,
    heal_req: Dict[str, Any],
) -> Optional[Tuple[str, str, Optional[Dict[str, Any]], float]]:
    heal_path = str(heal_req.get("path", "")).strip()
    if not heal_path:
        return None
    return (
        str(heal_req.get("method", "POST")).upper(),
        _resolve_heal_target(base_url, heal_path),
        heal_req.get("json") if isinstance(heal_req.get("json"), dict) else None,
        max(0.1, float(heal_req.get("timeout_s", 1.0))),
    )


def run_http_checks(
    base_url: str,
    checks: Dict[str, Any],
    default_timeout_ms: int = 1000,
    default_latency_warn_ms: int = 600,
    self_heal: Dict[str, Any] | None = None,
    notify: Dict[str, Any] | None = None,
    system_checks: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        import httpx  # type: ignore
    except Exception:
        return {"ok": False, "note": "httpx not installed", "failed": ["httpx"]}

    normalized = _normalize_checks(checks)
    out: Dict[str, Any] = {"ok": True, "failed": [], "degraded": []}
    heal_cfg = self_heal or {}
    heal_enabled = bool(heal_cfg.get("enabled", False))
    notify_cfg = notify or {}
    notify_enabled = bool(notify_cfg.get("enabled", False))
    notify_endpoint = str(notify_cfg.get("endpoint", "")).strip()

    client = httpx.Client(base_url=base_url)
    try:
        for name, chk in normalized.items():
            method = str(chk.get("method", "GET")).upper()
            path = str(chk.get("path", ""))
            timeout_ms = int(chk.get("timeout_ms", default_timeout_ms))
            latency_warn_ms = int(chk.get("latency_warn_ms", default_latency_warn_ms))
            critical = bool(chk.get("critical", True))
            heal_req = chk.get("heal") if isinstance(chk.get("heal"), dict) else None

            try:
                t0 = time.perf_counter()
                resp = client.request(method, path, timeout=max(0.1, timeout_ms / 1000.0))
                latency_ms = int((time.perf_counter() - t0) * 1000)
                ok, latency_only, entry = _evaluate_http_probe(
                    path, resp, latency_ms, latency_warn_ms, critical
                )
            except Exception as e:
                ok = False
                latency_only = False
                entry = {"ok": False, "critical": critical, "error": str(e)}

            heal_allowed, suppressed = _plan_heal(
                name,
                ok=ok,
                latency_only=latency_only,
                heal_req=heal_req,
                heal_cfg=heal_cfg,
            )
            if not ok:
                if suppressed is not None:
                    entry["heal_suppressed"] = suppressed
                if heal_enabled and heal_req is not None and heal_allowed:
                    heal_call = _prepare_heal_call(base_url, heal_req)
                    if heal_call is not None:
                        heal_method, target, heal_payload, heal_timeout = heal_call
                        try:
                            heal_resp = client.request(
                                heal_method,
                                target,
                                json=heal_payload,
                                timeout=heal_timeout,
                            )
                            entry["heal"] = {
                                "ok": bool(heal_resp.status_code < 500),
                                "status_code": int(heal_resp.status_code),
                                "target": target,
                            }
                        except Exception as heal_exc:
                            entry["heal"] = {"ok": False, "error": str(heal_exc), "target": target}

                if notify_enabled and notify_endpoint:
                    notify_url = _resolve_heal_target(base_url, notify_endpoint)
                    try:
                        client.request(
                            "POST",
                            notify_url,
                            json={"text": f"diagnostics: {name} failed", "source": "diagnostics"},
                            timeout=0.8,
                        )
                    except Exception as notify_exc:
                        logger.warning("Diagnostics notify POST to %s failed: %s", notify_url, notify_exc)

            _record_result(out, name, entry, ok=ok, critical=critical)
    finally:
        client.close()

    return _finalize_report(out, system_checks=system_checks)


async def run_http_checks_async(
    base_url: str,
    checks: Dict[str, Any],
    default_timeout_ms: int = 1000,
    default_latency_warn_ms: int = 600,
    self_heal: Dict[str, Any] | None = None,
    notify: Dict[str, Any] | None = None,
    system_checks: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run all configured HTTP health checks concurrently without blocking the event loop."""
    try:
        import httpx  # type: ignore
    except Exception:
        return {"ok": False, "note": "httpx not installed", "failed": ["httpx"]}

    normalized = _normalize_checks(checks)
    out: Dict[str, Any] = {"ok": True, "failed": [], "degraded": []}
    heal_cfg = self_heal or {}
    heal_enabled = bool(heal_cfg.get("enabled", False))
    notify_cfg = notify or {}
    notify_enabled = bool(notify_cfg.get("enabled", False))
    notify_endpoint = str(notify_cfg.get("endpoint", "")).strip()

    async with httpx.AsyncClient(base_url=base_url) as client:
        async def _check_one(name: str, chk: Dict[str, Any]) -> Tuple[str, bool, bool, Dict[str, Any]]:
            method = str(chk.get("method", "GET")).upper()
            path = str(chk.get("path", ""))
            timeout_ms = int(chk.get("timeout_ms", default_timeout_ms))
            latency_warn_ms = int(chk.get("latency_warn_ms", default_latency_warn_ms))
            critical = bool(chk.get("critical", True))
            heal_req = chk.get("heal") if isinstance(chk.get("heal"), dict) else None

            try:
                t0 = time.perf_counter()
                resp = await client.request(method, path, timeout=max(0.1, timeout_ms / 1000.0))
                latency_ms = int((time.perf_counter() - t0) * 1000)
                ok, latency_only, entry = _evaluate_http_probe(
                    path, resp, latency_ms, latency_warn_ms, critical
                )
            except Exception as e:
                ok = False
                latency_only = False
                entry = {"ok": False, "critical": critical, "error": str(e)}

            heal_allowed, suppressed = _plan_heal(
                name,
                ok=ok,
                latency_only=latency_only,
                heal_req=heal_req,
                heal_cfg=heal_cfg,
            )
            if not ok:
                if suppressed is not None:
                    entry["heal_suppressed"] = suppressed
                if heal_enabled and heal_req is not None and heal_allowed:
                    heal_call = _prepare_heal_call(base_url, heal_req)
                    if heal_call is not None:
                        heal_method, target, heal_payload, heal_timeout = heal_call
                        try:
                            heal_resp = await client.request(
                                heal_method,
                                target,
                                json=heal_payload,
                                timeout=heal_timeout,
                            )
                            entry["heal"] = {
                                "ok": bool(heal_resp.status_code < 500),
                                "status_code": int(heal_resp.status_code),
                                "target": target,
                            }
                        except Exception as heal_exc:
                            entry["heal"] = {"ok": False, "error": str(heal_exc), "target": target}

                if notify_enabled and notify_endpoint:
                    notify_url = _resolve_heal_target(base_url, notify_endpoint)
                    try:
                        await client.request(
                            "POST",
                            notify_url,
                            json={"text": f"diagnostics: {name} failed", "source": "diagnostics"},
                            timeout=0.8,
                        )
                    except Exception as notify_exc:
                        logger.warning("Diagnostics notify POST to %s failed: %s", notify_url, notify_exc)

            return name, ok, critical, entry

        results: List[Tuple[str, bool, bool, Dict[str, Any]]] = await asyncio.gather(
            *(_check_one(name, chk) for name, chk in normalized.items())
        )
        for name, ok, critical, entry in results:
            _record_result(out, name, entry, ok=ok, critical=critical)

    return _finalize_report(out, system_checks=system_checks)
