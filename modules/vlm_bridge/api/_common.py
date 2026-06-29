from __future__ import annotations
import requests


def gw(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def notify_autonomy(base_url: str):
    try:
        requests.post(gw(base_url, "/autonomy/interaction"), timeout=0.1)
    except Exception:
        pass


def request_arduino(base_url: str, payload: dict, timeout: float = 1.0) -> dict:
    resp = requests.post(
        gw(base_url, "/arduino/request"),
        json=payload,
        params={"timeout": float(timeout)},
        timeout=max(0.2, float(timeout) + 0.2),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"gateway arduino request failed: HTTP {resp.status_code}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("gateway arduino response is not JSON object")
    return data
