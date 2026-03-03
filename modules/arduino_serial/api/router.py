from __future__ import annotations
from fastapi import APIRouter
from typing import Optional, Dict, Any

try:
    from ..xArduinoSerialService import xArduinoSerialService
except Exception:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore


def get_router(svc: xArduinoSerialService) -> APIRouter:
    r = APIRouter(prefix="/arduino")

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
        try:
            svc.send(obj)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/request")
    def request(obj: Dict[str, Any], timeout: float = 1.0):
        try:
            resp = svc.request(obj, timeout=timeout)
            return {"ok": True, "resp": resp}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/telemetry/start")
    def telemetry_start(interval_ms: int = 100):
        try:
            return svc.telemetry_start(interval_ms)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/telemetry/stop")
    def telemetry_stop():
        try:
            return svc.telemetry_stop()
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
        try:
            return svc.laser_on(which)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/laser/both")
    def laser_both():
        try:
            return svc.laser_both_on()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/laser/off")
    def laser_off():
        try:
            return svc.laser_off()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/cute/{name}")
    def cute(name: str):
        try:
            return svc.cute(name)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/sound/out/{mode}")
    def sound_out(mode: str):
        try:
            return svc.sound_output(mode)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/buzzer")
    def buzzer(freq: int = 2200, ms: int = 60, out: Optional[str] = None):
        try:
            return svc.buzzer(freq=freq, ms=ms, out=out)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/sound/play/{name}")
    def sound_play(name: str, out: Optional[str] = None):
        try:
            return svc.sound_play(name=name, out=out)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.get("/cute/catalog")
    def cute_catalog():
        try:
            return svc.get_cute_catalog()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.get("/metrics")
    def metrics():
        try:
            return svc._metrics
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/cute/emotion/{emotion}")
    def cute_emotion(emotion: str):
        try:
            return svc.play_emotion(emotion)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return r
