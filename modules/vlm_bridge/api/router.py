from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from typing import Optional, Any
import logging
import requests
from modules.arduino_serial.contract import build_track_cmd

def _notify_autonomy():
    try:
        requests.post("http://localhost:8080/autonomy/interaction", timeout=0.1)
    except Exception:
        pass

def _request_arduino(payload: dict, timeout: float = 1.0) -> dict:
    resp = requests.post(
        "http://127.0.0.1:8080/arduino/request",
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


def get_router(processor: Any, ardu: Optional[Any] = None) -> APIRouter:
    r = APIRouter(
        prefix="/vlm",
        tags=["vlm"],
        responses={404: {"description": "Not found"}},
    )

    @r.post("/track", tags=["control"], summary="Pan/Tilt tracking control")
    def track(head_tilt: float, head_pan: float, drive: int | None = None, background_tasks: BackgroundTasks = None):
        if background_tasks:
            background_tasks.add_task(_notify_autonomy)
            
        payload = build_track_cmd(head_tilt=head_tilt, head_pan=head_pan, drive=(int(drive) if drive is not None else None))
        try:
            data = _request_arduino(payload, timeout=1.0)
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

    @r.get("/mode", tags=["control"], summary="Get active mode/profile flags")
    def get_mode():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        modes = processor.get_modes() if hasattr(processor, "get_modes") else {}
        profiles = processor.list_profiles() if hasattr(processor, "list_profiles") else []
        return {
            "ok": True,
            "processing_mode": getattr(processor, "processing_mode", "unknown"),
            "modes": modes,
            "profiles": profiles,
        }

    @r.get("/profile", tags=["control"], summary="Get realtime latency profile")
    def get_profile():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if hasattr(processor, "get_realtime_profile_status"):
            return processor.get_realtime_profile_status()
        return {"ok": False, "error": "profile control not available"}

    @r.post("/profile/switch", tags=["control"], summary="Switch realtime latency profile")
    def switch_profile(body: dict):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        mode = str((body or {}).get("mode", "")).strip().lower()
        if not mode:
            raise HTTPException(status_code=400, detail="mode required")
        if hasattr(processor, "apply_realtime_profile"):
            return processor.apply_realtime_profile(mode)
        return {"ok": False, "error": "profile control not available"}

    @r.post("/mode", tags=["control"], summary="Set processing mode and/or mode flags")
    def set_mode(body: dict):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be object")

        out: dict = {"ok": True}

        processing_mode = body.get("processing_mode")
        if processing_mode is not None and hasattr(processor, "set_processing_mode"):
            out["processing_mode"] = processor.set_processing_mode(str(processing_mode))

        profile = body.get("profile")
        if profile is not None and hasattr(processor, "apply_mode_profile"):
            out["profile"] = processor.apply_mode_profile(str(profile))

        modes = body.get("modes")
        if isinstance(modes, dict) and hasattr(processor, "set_modes"):
            out["modes_update"] = processor.set_modes(modes)

        out["modes"] = processor.get_modes() if hasattr(processor, "get_modes") else {}
        out["processing_mode_current"] = getattr(processor, "processing_mode", "unknown")
        return out

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

    @r.get("/results/latest", tags=["remote"], summary="Get last cached detections")
    def latest_results(limit: int = 10):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "latest_results"):
            raise HTTPException(status_code=503, detail="Vision processor missing latest_results interface")
        limit = max(0, int(limit))
        results = list(getattr(processor, "latest_results", []) or [])
        if limit:
            results = results[:limit]
        return {"results": results, "count": len(results)}

    @r.post("/results", tags=["remote"], summary="Ingest remote detection results")
    def ingest_results(request: Request, payload: dict):
        """External processor posts detection results.

        Expected JSON: {"objects": [...], "frame_id": int?, "timestamp": float?}
        Security: X-Auth-Token header must match config remote.auth_token.
        """
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "config") or not hasattr(processor, "ingest_remote_results"):
            raise HTTPException(status_code=503, detail="Vision processor missing remote ingestion interface")

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
        logger = logging.getLogger("vlm_bridge.api.router")

        # Primary attempt: use processor's current frame (requires stream running)
        try:
            success = processor.register_face_from_current_frame(name)
        except Exception as e:
            logger.debug("register_face primary attempt failed: %s", e)
            success = False

        if success:
            return {"status": "success", "message": f"Registered face for {name}"}

        # Fallback: attempt one-shot capture directly from camera (no stream required)
        try:
            import cv2
            cap = cv2.VideoCapture(processor.camera_source)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    try:
                        ok = processor.face_manager.register_face(name, frame)
                        if ok:
                            return {"status": "success", "message": f"Registered face for {name} (one-shot)"}
                    except Exception as e:
                        logger.debug("register_face one-shot encoding failed: %s", e)
        except Exception as e:
            logger.debug("register_face fallback capture failed: %s", e)

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

    # -----------------------------------------------------------------
    # Living Vision Agent endpoints
    # -----------------------------------------------------------------

    @r.get("/context/latest", tags=["vision"], summary="Get latest visual context cache")
    def get_context_latest():
        """Return the latest cached VisionFrameContext if available."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        ctx = processor.get_latest_visual_context()
        if ctx is None:
            return {"available": False, "context": None, "reason": "No context cached yet"}
        return {"available": True, "context": ctx}

    @r.post("/context/refresh", tags=["vision"], summary="Refresh visual context (trigger VLM analysis)")
    def refresh_context():
        """Trigger a fresh VLM analysis of the current camera frame."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")

        if hasattr(processor, "refresh_visual_context"):
            ctx = processor.refresh_visual_context()
        else:
            ctx = processor.get_latest_visual_context()
        return {"ok": True, "context_available": ctx is not None, "context": ctx}

    @r.post("/ask", tags=["vision"], summary="Ask the VLM a question about the current scene")
    def ask_vlm(body: dict):
        """Ask the VLM a question about the current camera view."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        
        question = body.get("question", "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="question required")
        
        # Try to get current frame first
        frame = None
        with processor._frame_lock:
            if processor._latest_raw_frame is not None:
                frame = processor._latest_raw_frame.copy()
        
        # If no current frame from stream, try one-shot capture
        if frame is None and not processor._is_http_camera_source():
            try:
                import cv2
                cap = cv2.VideoCapture(processor.camera_source)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if not ret:
                        frame = None
            except Exception:
                pass
        
        if frame is None:
            # Fallback to cached context
            ctx = processor.get_latest_visual_context()
            if ctx:
                return {"ok": True, "answer": ctx.get("persona_interpretation", ctx.get("summary", "Görüntü işlenemedi."))}
            return {"ok": False, "answer": "Kamera görüntüsü alınamadı."}
        
        # Call VLM if available
        if processor.vlm_client:
            try:
                answer = processor.vlm_client.ask_about_scene(frame, question, force=True)
                if answer:
                    if hasattr(processor, "refresh_visual_context"):
                        processor.refresh_visual_context(question=question)
                    return {"ok": True, "answer": answer}
            except Exception:
                pass
        
        # Fallback: context interpretation
        ctx = processor.get_latest_visual_context()
        if ctx:
            summary = ctx.get("persona_interpretation", ctx.get("summary", "Cevap alınamadı."))
            return {"ok": True, "answer": f"Görüntü işleme gecikti; elimdeki son görüntüye göre {summary}"}
        
        return {"ok": False, "answer": "VLM sistemi şu an kullanılamıyor."}

    @r.post("/person/remember", tags=["vision"], summary="Remember/store person with relationship")
    def remember_person(body: dict):
        """Save or update a person in the identity memory."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not processor.person_identity:
            raise HTTPException(status_code=501, detail="Person identity system not available")
        
        name = body.get("name", "").strip()
        relationship = body.get("relationship", "known")
        recognition_level = body.get("recognition_level", 2)
        
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        
        rec = processor.person_identity.remember_person(
            name, relationship=relationship, recognition_level=int(recognition_level)
        )
        return {
            "ok": True,
            "person_id": rec.person_id,
            "name": rec.name,
            "recognition_level": rec.recognition_level,
            "relationship": rec.relationship,
        }

    @r.post("/person/relationship", tags=["vision"], summary="Update person's relationship/recognition level")
    def update_person_relationship(body: dict):
        """Update a person's relationship or recognition level."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not processor.person_identity:
            raise HTTPException(status_code=501, detail="Person identity system not available")
        
        person_id = body.get("person_id", "").strip()
        name = body.get("name", "").strip()
        relationship = body.get("relationship", "")
        recognition_level = body.get("recognition_level", -1)
        
        if not person_id and not name:
            raise HTTPException(status_code=400, detail="person_id or name required")
        
        # Support lookup by either person_id or name
        if name and not person_id:
            # Try to find by name
            records = processor.person_identity._records
            for rec in records.values():
                if rec.name.lower() == name.lower():
                    person_id = rec.person_id
                    break
        
        if person_id:
            rec = processor.person_identity._records.get(person_id)
            if rec:
                if relationship:
                    rec.relationship = relationship
                if recognition_level >= 0:
                    rec.recognition_level = min(5, max(0, int(recognition_level)))
                processor.person_identity._save_unlocked()
                return {"ok": True, "person_id": rec.person_id, "name": rec.name}
        
        return {"ok": False, "error": "person not found"}

    @r.get("/person/{name}", tags=["vision"], summary="Get person memory record by name")
    def get_person(name: str):
        """Retrieve a person's memory record."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not processor.person_identity:
            raise HTTPException(status_code=501, detail="Person identity system not available")
        
        rec = processor.person_identity.recognize(name)
        if rec is None:
            return {"ok": False, "error": "person not found"}
        return {"ok": True, "person": rec.to_dict() if hasattr(rec, "to_dict") else rec}

    @r.get("/people", tags=["vision"], summary="List all remembered people")
    def list_people():
        """List all people in the identity memory."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not processor.person_identity:
            return {"people": []}
        
        people = []
        for rec in processor.person_identity._records.values():
            people.append({
                "person_id": rec.person_id,
                "name": rec.name,
                "recognition_level": rec.recognition_level,
                "relationship": rec.relationship,
                "seen_count": rec.seen_count,
                "last_seen": rec.last_seen,
            })
        return {"people": people}

    @r.post("/focus/person", tags=["vision"], summary="Focus head on specific person")
    def focus_person(body: dict):
        """Request the robot to look at a specific person."""
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

    @r.post("/follow/owner/start", tags=["vision"], summary="Start owner follow mode")
    def owner_follow_start():
        """Enable owner-specific follow mode (higher priority)."""
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        
        result = processor.start_follow(person="owner")
        return result if isinstance(result, dict) else {"ok": True}

    @r.get("/head/status", tags=["vision"], summary="Get current head (pan/tilt) position")
    def head_status():
        """Return the current head servo position."""
        if processor and hasattr(processor, "head_arbiter") and processor.head_arbiter is not None:
            return processor.head_arbiter.get_status()
        return {"pan": 90, "tilt": 90}

    return r

