from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from typing import Optional, Any
import requests

try:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
except (ImportError, ModuleNotFoundError):
    try:
        from ..services.stub import xArduinoSerialService  # type: ignore
    except (ImportError, ValueError):
        # Fallback for script execution where relative import fails
        from services.stub import xArduinoSerialService  # type: ignore

# Shared singleton to avoid re-creating serial per request (fallback only)
_ardu_singleton: Optional[xArduinoSerialService] = None

def _notify_autonomy():
    try:
        requests.post("http://localhost:8080/autonomy/interaction", timeout=0.1)
    except Exception:
        pass

def _get_or_create_ardu() -> xArduinoSerialService:
    global _ardu_singleton
    if _ardu_singleton is None:
        # Same import logic here
        try:
            from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
            _ardu_singleton = xArduinoSerialService()
        except (ImportError, ModuleNotFoundError):
            try:
                from ..services.stub import xArduinoSerialService  # type: ignore
                _ardu_singleton = xArduinoSerialService()
            except (ImportError, ValueError):
                from services.stub import xArduinoSerialService  # type: ignore
                _ardu_singleton = xArduinoSerialService()
                
        _ardu_singleton.start()
    return _ardu_singleton


def get_router(processor: Any, ardu: Optional[xArduinoSerialService] = None) -> APIRouter:
    r = APIRouter(
        prefix="/vision",
        tags=["vision"],
        responses={404: {"description": "Not found"}},
    )

    @r.post("/track", tags=["control"], summary="Pan/Tilt tracking control")
    def track(head_tilt: float, head_pan: float, drive: int | None = None, background_tasks: BackgroundTasks = None):
        if background_tasks:
            background_tasks.add_task(_notify_autonomy)
            
        svc = ardu or _get_or_create_ardu()
        payload = {"cmd": "track", "head_tilt": head_tilt, "head_pan": head_pan}
        if drive is not None:
            payload["drive"] = int(drive)
        try:
            resp = svc.request(payload, timeout=1.0)
            return {"ok": bool(resp.get("ok", False)), "resp": resp}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @r.post("/analyze", tags=["analysis"], summary="Analyze single frame (local)")
    def analyze_snapshot():
        """Trigger a one-off analysis of the current view (local mode)."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        results = processor.analyze_snapshot()
        return {"results": results}

    @r.post("/blind/start", tags=["assistive"], summary="Start assistive blind mode")
    def start_blind_mode():
        """Enable continuous blind mode description."""
        if not processor:
             raise HTTPException(status_code=503, detail="Vision processor not initialized")
        
        processor.blind_mode_enabled = True
        processor.start_stream_processing()
        return {"status": "Blind mode started"}

    @r.post("/blind/stop", tags=["assistive"], summary="Stop assistive blind mode")
    def stop_blind_mode():
        """Disable blind mode."""
        if not processor:
             raise HTTPException(status_code=503, detail="Vision processor not initialized")
        
        processor.blind_mode_enabled = False
        # We don't necessarily stop the stream if other things need it, 
        # but for now we can stop it to save resources if nothing else uses it.
        # processor.stop_stream_processing() 
        return {"status": "Blind mode stopped"}

    @r.get("/video_feed", tags=["stream"], summary="Annotated MJPEG stream (local)")
    def video_feed():
        """Stream video with annotations (local mode only)."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if processor.processing_mode != "local":
            raise HTTPException(status_code=400, detail="Video feed not available in remote mode")
        processor.start_stream_processing()
        from fastapi.responses import StreamingResponse
        return StreamingResponse(processor.generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @r.post("/results", tags=["remote"], summary="Ingest remote detection results")
    def ingest_results(request: Request, payload: dict):
        """External processor posts detection results.

        Expected JSON: {"objects": [...], "frame_id": int?, "timestamp": float?}
        Security: X-Auth-Token header must match config remote.auth_token.
        """
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")

        cfg_remote = processor.config.get("remote", {})
        if not cfg_remote.get("accept_results", True):
            raise HTTPException(status_code=403, detail="Remote result ingestion disabled")

        auth_required = cfg_remote.get("auth_token")
        provided = request.headers.get("X-Auth-Token")
        if auth_required and auth_required != "changeme" and auth_required != provided:
            raise HTTPException(status_code=401, detail="Invalid auth token")

        objects = payload.get("objects", [])
        summary = processor.ingest_remote_results(objects)
        return {"ok": True, "summary": summary}

    @r.post("/faces/register", tags=["faces"], summary="Register current face with name")
    def register_face(name: str):
        """Register the face currently visible in the camera."""
        if not processor:
             raise HTTPException(status_code=503, detail="Vision processor not initialized")
        
        if not processor.face_manager:
             raise HTTPException(status_code=501, detail="Face recognition not available")

        success = processor.register_face_from_current_frame(name)
        if success:
            return {"status": "success", "message": f"Registered face for {name}"}
        else:
            return {"status": "failed", "message": "No face detected or encoding failed"}

    @r.get("/faces", tags=["faces"], summary="List known faces")
    def list_faces():
        """List known faces."""
        if not processor or not processor.face_manager:
            return {"faces": []}
        return {"faces": processor.face_manager.known_face_names}

    @r.post("/memory/chat", tags=["memory"], summary="Append chat to person's memory")
    def memory_chat(person: str, text: str, role: str = "assistant"):
        """Append a chat line to a person's memory (for Ollama chat integration)."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        processor.record_chat(person, text, role)
        return {"ok": True}

    @r.get("/memory/person", tags=["memory"], summary="Get person memory record")
    def memory_get(person: str):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        rec = processor.memory.get_person(person)
        return {"person": person, "record": rec}

    @r.get("/memory/people", tags=["memory"], summary="List people in memory")
    def memory_list():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        return {"people": processor.memory.list_people()}

    return r
