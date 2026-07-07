from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import Any, Optional
from modules.arduino_serial.contract import build_track_cmd
from modules.vlm_bridge.api._common import gw, notify_autonomy, request_arduino


def get_control_router(processor: Any, ardu: Optional[Any], base_url: str) -> APIRouter:
    r = APIRouter(tags=["vlm-control"])

    @r.post("/track", tags=["control"], summary="Pan/Tilt tracking control")
    def track(head_tilt: float, head_pan: float, drive: int | None = None, background_tasks: BackgroundTasks = None):
        if background_tasks:
            background_tasks.add_task(notify_autonomy, base_url)

        payload = build_track_cmd(head_tilt=head_tilt, head_pan=head_pan, drive=(int(drive) if drive is not None else None))
        try:
            data = request_arduino(base_url, payload, timeout=1.0)
            resp = data.get("resp") if isinstance(data, dict) and "resp" in data else data
            return {"ok": bool(resp.get("ok", False)), "resp": resp}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/follow/start", tags=["control"], summary="Start face follow mode")
    def follow_start(person: str | None = None):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "start_follow"):
            raise HTTPException(status_code=503, detail="Vision processor missing follow interface")
        result = processor.start_follow(person=person)
        return result if isinstance(result, dict) else {"ok": True}

    @r.post("/follow/stop", tags=["control"], summary="Stop face follow mode")
    def follow_stop():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "stop_follow"):
            raise HTTPException(status_code=503, detail="Vision processor missing follow interface")
        result = processor.stop_follow()
        return result if isinstance(result, dict) else {"ok": True}

    @r.get("/follow/status", tags=["control"], summary="Face follow state")
    def follow_status():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "follow_status"):
            raise HTTPException(status_code=503, detail="Vision processor missing follow interface")
        result = processor.follow_status()
        return result if isinstance(result, dict) else {"active": False}

    @r.post("/follow/owner/start", tags=["vision"], summary="Start owner follow mode")
    def owner_follow_start():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        result = processor.start_follow(person="owner")
        return result if isinstance(result, dict) else {"ok": True}

    @r.post("/focus/person", tags=["vision"], summary="Focus head on specific person")
    def focus_person(body: dict):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")

        name = body.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")

        if hasattr(processor, "latest_results"):
            for item in list(getattr(processor, "latest_results", []) or []):
                if str(item.get("name", "")).strip().lower() == name.lower():
                    bbox = item.get("bbox") or []
                    if len(bbox) == 4:
                        try:
                            x1, y1, x2, y2 = [int(v) for v in bbox]
                            cx = int((x1 + x2) / 2)
                            cy = int((y1 + y2) / 2)
                            pan = max(35, min(145, int(90 + ((cx - 320) / 320) * 45)))
                            tilt = max(65, min(125, int(90 + ((cy - 240) / 240) * 30)))
                            if hasattr(processor, "head_arbiter") and processor.head_arbiter is not None:
                                from modules.vlm_bridge.services.head_control_arbiter import HeadCommand
                                result = processor.head_arbiter.request_move(
                                    HeadCommand(pan=float(pan), tilt=float(tilt), source="agent_core", priority=65, ttl_s=1.0)
                                )
                                return {"ok": bool(result.get("ok")), "focus_target": name, "head": result}
                            processor._send_track(pan=pan, tilt=tilt, drive=0)
                            return {"ok": True, "focus_target": name, "pan": pan, "tilt": tilt}
                        except Exception:
                            pass
        return {"ok": False, "error": "person_not_visible", "focus_target": name}

    @r.get("/head/status", tags=["vision"], summary="Get current head (pan/tilt) position")
    def head_status():
        if processor and hasattr(processor, "head_arbiter") and processor.head_arbiter is not None:
            return processor.head_arbiter.get_status()
        return {"pan": 90, "tilt": 90}

    @r.post("/head/move", tags=["vision"], summary="Request pan/tilt via head arbiter")
    def head_move(body: dict):
        if not processor or not hasattr(processor, "head_arbiter") or processor.head_arbiter is None:
            raise HTTPException(status_code=503, detail="Head arbiter not initialized")
        from modules.vlm_bridge.services.head_control_arbiter import HeadCommand

        pan = float(body.get("pan", 90))
        tilt = float(body.get("tilt", 90))
        source = str(body.get("source", "agent_core"))
        priority = int(body.get("priority", 60))
        result = processor.head_arbiter.request_move(
            HeadCommand(pan=pan, tilt=tilt, source=source, priority=priority, ttl_s=float(body.get("ttl_s", 1.5)))
        )
        return result

    return r
