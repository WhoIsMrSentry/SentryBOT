from __future__ import annotations
import argparse, json, time
from typing import Any
import requests

def call(method: str, base: str, path: str, payload: Any = None, timeout: float = 15.0) -> dict:
    url = base.rstrip("/") + path
    try:
        if method == "GET": r = requests.get(url, timeout=timeout)
        else: r = requests.post(url, json=payload or {}, timeout=timeout)
        try: body = r.json()
        except Exception: body = r.text[-2000:]
        return {"path": path, "status": r.status_code, "ok": 200 <= r.status_code < 300, "body": body}
    except Exception as e:
        return {"path": path, "status": 0, "ok": False, "error": str(e)}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--allow-motion", action="store_true")
    args = ap.parse_args()
    steps = []
    for path in ["/health", "/autonomy/assets/status", "/autonomy/pi-runtime/status", "/autonomy/living-needs", "/autonomy/navigation/topomap", "/autonomy/owner/status"]:
        steps.append(call("GET", args.base, path))
    steps.append(call("POST", args.base, "/autonomy/living-needs/tick", {"seconds": 900, "social_contact": False, "person_visible": False, "resting": False}))
    steps.append(call("POST", args.base, "/autonomy/sound-interrupt", {"source": "test", "confidence": 0.9, "azimuth": 0.0}))
    steps.append(call("POST", args.base, "/autonomy/scenario/companion-e2e", {"reason": "batch05_robot_test", "allow_motion": bool(args.allow_motion)} , timeout=30.0))
    ok_required = all(s.get("ok") for s in steps[:6])
    result = {"ok": ok_required, "base": args.base, "allow_motion": args.allow_motion, "steps": steps, "ts": time.time()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok_required else 2
if __name__ == "__main__":
    raise SystemExit(main())
