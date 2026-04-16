from __future__ import annotations
from typing import Dict, Any, Tuple
import time


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


def run_http_checks(
    base_url: str,
    checks: Dict[str, Any],
    default_timeout_ms: int = 1000,
    default_latency_warn_ms: int = 600,
    self_heal: Dict[str, Any] | None = None,
    notify: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        import httpx  # type: ignore
    except Exception:
        return {"ok": True, "note": "httpx not installed; skipped"}

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

            try:
                t0 = time.perf_counter()
                resp = client.request(method, path, timeout=max(0.1, timeout_ms / 1000.0))
                latency_ms = int((time.perf_counter() - t0) * 1000)
                status_ok = resp.status_code == 200
                latency_ok = latency_ms <= latency_warn_ms
                ok = bool(status_ok and latency_ok)
                out[name] = {
                    "ok": ok,
                    "critical": critical,
                    "status_code": int(resp.status_code),
                    "latency_ms": latency_ms,
                    "latency_warn_ms": latency_warn_ms,
                    "within_latency": latency_ok,
                }

                if not ok:
                    if critical:
                        out["failed"].append(name)
                    else:
                        out["degraded"].append(name)

                    if heal_enabled and isinstance(chk.get("heal"), dict):
                        heal_req = chk.get("heal") or {}
                        heal_method = str(heal_req.get("method", "POST")).upper()
                        heal_path = str(heal_req.get("path", "")).strip()
                        heal_payload = heal_req.get("json") if isinstance(heal_req.get("json"), dict) else None
                        heal_timeout = float(heal_req.get("timeout_s", 1.0))
                        if heal_path:
                            target = _resolve_heal_target(base_url, heal_path)
                            try:
                                heal_resp = client.request(
                                    heal_method,
                                    target,
                                    json=heal_payload,
                                    timeout=max(0.1, heal_timeout),
                                )
                                out[name]["heal"] = {
                                    "ok": bool(heal_resp.status_code < 500),
                                    "status_code": int(heal_resp.status_code),
                                    "target": target,
                                }
                            except Exception as heal_exc:
                                out[name]["heal"] = {
                                    "ok": False,
                                    "error": str(heal_exc),
                                    "target": target,
                                }

                    if notify_enabled and notify_endpoint:
                        try:
                            client.post(
                                notify_endpoint,
                                json={"text": f"diagnostics: {name} failed", "source": "diagnostics"},
                                timeout=0.8,
                            )
                        except Exception:
                            pass

                if critical and not ok:
                    out["ok"] = False
            except Exception as e:
                out[name] = {"ok": False, "critical": critical, "error": str(e)}
                if critical:
                    out["failed"].append(name)
                    out["ok"] = False
                else:
                    out["degraded"].append(name)
    finally:
        client.close()

    # If no critical checks failed, overall health is still true.
    if not out.get("failed"):
        out["ok"] = True
    return out
