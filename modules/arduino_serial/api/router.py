from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from ..contract import validate_arduino_payload
from ..xArduinoSerialService import xArduinoSerialService

logger = logging.getLogger("arduino_serial.router")


def get_router(svc: xArduinoSerialService) -> APIRouter:
    def _validate_payload_or_400(obj: Dict[str, Any]) -> None:
        err = validate_arduino_payload(obj)
        if err:
            raise HTTPException(status_code=400, detail=err)

    r = APIRouter(prefix="/arduino")

    def _safe_call(fn):
        try:
            return fn()
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            msg = str(exc)
            if "denied by arbiter" in msg.lower() or "arbiter" in msg.lower():
                raise HTTPException(status_code=403, detail=msg) from exc
            raise HTTPException(status_code=503, detail=msg) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("arduino router unhandled error")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @r.get("/healthz")
    def healthz():
        try:
            resp = svc.hello()
            ok = bool(resp.get("ok", False))
        except Exception as exc:
            logger.debug("arduino healthz probe failed: %s", exc)
            ok = False
            resp = {"ok": False}
        fw_info = svc.get_firmware_info() if hasattr(svc, "get_firmware_info") else {}
        if fw_info.get("checked") and not fw_info.get("compatible", True):
            ok = False
        return {"ok": ok, "resp": resp, "firmware": fw_info}

    @r.get("/watchdog/status")
    def watchdog_status():
        wd = getattr(svc, "watchdog", None)
        if wd is None:
            return {"ok": True, "enabled": False}
        return {"ok": True, "enabled": True, **wd.status()}

    @r.post("/watchdog/reset")
    def watchdog_reset():
        wd = getattr(svc, "watchdog", None)
        if wd is None:
            raise HTTPException(status_code=503, detail="safety watchdog disabled")
        wd.reset_trip()
        return {"ok": True, **wd.status()}

    @r.post("/send")
    def send(obj: Dict[str, Any]):
        _validate_payload_or_400(obj)

        def _do_send():
            svc.send(obj)
            return {"ok": True}

        return _safe_call(_do_send)

    @r.post("/request")
    def request(obj: Dict[str, Any], timeout: Optional[float] = None):
        _validate_payload_or_400(obj)

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
        return _safe_call(svc.get_metrics)

    @r.post("/cute/emotion/{emotion}")
    def cute_emotion(emotion: str):
        return _safe_call(lambda: svc.play_emotion(emotion))

    return r
