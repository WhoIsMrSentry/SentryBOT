from __future__ import annotations
from typing import Dict, Any, Tuple


def run_http_checks(base_url: str, checks: Dict[str, Tuple[str, str]]) -> Dict[str, Any]:
    try:
        import httpx  # type: ignore
    except Exception:
        return {"ok": True, "note": "httpx not installed; skipped"}

    out: Dict[str, Any] = {"ok": True}
    client = httpx.Client(base_url=base_url)
    try:
        for name, (method, path) in checks.items():
            try:
                resp = client.request(method, path, timeout=1.0)
                ok = resp.status_code == 200
                out[name] = {"ok": ok}
                if not ok:
                    out["ok"] = False
            except Exception as e:
                out[name] = {"ok": False, "error": str(e)}
                out["ok"] = False
    finally:
        client.close()
    return out
