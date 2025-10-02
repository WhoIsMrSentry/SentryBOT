from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter


def get_router(cfg: Dict[str, Any], started: Dict[str, object]) -> APIRouter:
    r = APIRouter()

    @r.get("/healthz")
    def healthz():
        out: Dict[str, Any] = {"ok": True, "modules": {}}
        # Try to call each module's health if known, else mark as started
        try:
            import httpx  # type: ignore
        except Exception:
            httpx = None  # type: ignore
        port = int(cfg.get("server", {}).get("port", 8080))
        client = None
        if httpx:
            client = httpx.Client(base_url=f"http://127.0.0.1:{port}")
        try:
            for name in started.keys():
                path = None
                if name in ("arduino", "neopixel", "piservo", "telemetry", "diagnostics", "state_manager", "scheduler", "notifier", "calibration", "config_center", "hardware"):
                    path = f"/{name}/healthz" if name not in ("telemetry", "diagnostics") else f"/{name}/healthz"
                elif name == "camera":
                    path = "/camera/healthz"
                elif name in ("speak", "speech"):
                    path = f"/{name}/status"
                elif name in ("wiki_rag",):
                    path = "/wiki_rag/healthz"
                if client and path:
                    try:
                        resp = client.get(path, timeout=0.5)
                        ok = resp.status_code == 200
                        out["modules"][name] = {"ok": ok}
                        if not ok:
                            out["ok"] = False
                    except Exception as e:
                        out["modules"][name] = {"ok": False, "error": str(e)}
                        out["ok"] = False
                else:
                    out["modules"][name] = {"ok": True}
        finally:
            if client:
                client.close()
        return out

    @r.get("/status")
    def status():
        include_cfg = dict(cfg.get("include", {}))
        started_names = list(started.keys())
        configured_on = [k for k, v in include_cfg.items() if bool(v)]
        not_started = [k for k in configured_on if k not in started_names]
        return {
            "ok": True,
            "configured": include_cfg,
            "started": started_names,
            "not_started": not_started,
        }

    @r.get("/health")
    def health():
        try:
            import httpx  # type: ignore
        except Exception:
            return {"ok": True, "note": "httpx not installed; basic status only", "included": list(started.keys())}

        summary: Dict[str, Any] = {"ok": True}
        checks = {
            "arduino": ("GET", "/arduino/healthz"),
            "neopixel": ("GET", "/neopixel/healthz"),
            "piservo": ("GET", "/piservo/healthz"),
            "speech": ("GET", "/speech/status"),
            "speak": ("GET", "/speak/status"),
            "vision_bridge": None,
            "interactions": None,
            "ollama": ("GET", "/ollama/healthz"),
        }
        mounted_checks = {
            "camera": ("GET", "/camera/healthz"),
            "wiki_rag": ("GET", "/wiki_rag/healthz"),
        }
        port = int(cfg.get("server", {}).get("port", 8080))
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}")
        try:
            for name, _ in started.items():
                if name in checks and checks[name] is not None:
                    method, path = checks[name]
                    try:
                        resp = client.request(method, path, timeout=0.5)
                        summary[name] = {"ok": resp.status_code == 200, "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None}
                        if not summary[name]["ok"]:
                            summary["ok"] = False
                    except Exception as e:
                        summary[name] = {"ok": False, "error": str(e)}
                        summary["ok"] = False
                elif name in mounted_checks:
                    method, path = mounted_checks[name]
                    try:
                        resp = client.request(method, path, timeout=0.5)
                        summary[name] = {"ok": resp.status_code == 200, "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None}
                        if not summary[name]["ok"]:
                            summary["ok"] = False
                    except Exception as e:
                        summary[name] = {"ok": False, "error": str(e)}
                        summary["ok"] = False
                else:
                    summary[name] = {"ok": True}
        finally:
            client.close()
        return summary

    return r
