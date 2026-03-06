from __future__ import annotations
from fastapi import APIRouter
from typing import Optional, Dict, Any

try:
    from ..xArduinoSerialService import xArduinoSerialService
except Exception:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore


def get_router(svc: xArduinoSerialService) -> APIRouter:
    r = APIRouter(prefix="/arduino")

    def _safe_call(fn):
        try:
            return fn()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @r.get("/healthz")
    def healthz():
        # try ping
        try:
            resp = svc.hello()
            ok = bool(resp.get("ok", False))
        except Exception:
            ok = False
            resp = {"ok": False}
        return {"ok": ok, "resp": resp}

    @r.post("/send")
    def send(obj: Dict[str, Any]):
        def _do_send():
            svc.send(obj)
            return {"ok": True}
        return _safe_call(_do_send)

    @r.post("/request")
    def request(obj: Dict[str, Any], timeout: float = 1.0):
        def _do_request():
            resp = svc.request(obj, timeout=timeout)
            return {"ok": True, "resp": resp}
        return _safe_call(_do_request)

    @r.post("/telemetry/start")
    def telemetry_start(interval_ms: int = 100):
        return _safe_call(lambda: svc.telemetry_start(interval_ms))

    @r.post("/telemetry/stop")
    def telemetry_stop():
        return _safe_call(svc.telemetry_stop)

    @r.get("/rfid/last")
    def rfid_last():
        snap = svc.get_last_rfid()
        if not snap:
            return {"ok": False, "error": "no_rfid"}
        return {"ok": True, **snap}

    @r.get("/rfid/authorize")
    def rfid_authorize(uid: Optional[str] = None, window_s: Optional[float] = None):
        result = svc.authorize_rfid(uid=uid, window_s=window_s)
        ok = bool(result.get("authorized"))
        return {"ok": ok, **result}

    # Laser controls
    @r.post("/laser/one/{which}")
    def laser_one(which: int):
        return _safe_call(lambda: svc.laser_on(which))

    @r.post("/laser/both")
    def laser_both():
        return _safe_call(svc.laser_both_on)

    @r.post("/laser/off")
    def laser_off():
        return _safe_call(svc.laser_off)

    @r.post("/cute/{name}")
    def cute(name: str):
        return _safe_call(lambda: svc.cute(name))

    @r.post("/sound/out/{mode}")
    def sound_out(mode: str):
        return _safe_call(lambda: svc.sound_output(mode))

    @r.post("/buzzer")
    def buzzer(freq: int = 2200, ms: int = 60, out: Optional[str] = None):
        return _safe_call(lambda: svc.buzzer(freq=freq, ms=ms, out=out))

    @r.post("/sound/play/{name}")
    def sound_play(name: str, out: Optional[str] = None):
        return _safe_call(lambda: svc.sound_play(name=name, out=out))

    @r.get("/cute/catalog")
    def cute_catalog():
        return _safe_call(svc.get_cute_catalog)

    @r.get("/metrics")
    def metrics():
        return _safe_call(lambda: svc._metrics)

    @r.post("/cute/emotion/{emotion}")
    def cute_emotion(emotion: str):
        return _safe_call(lambda: svc.play_emotion(emotion))

    return r
