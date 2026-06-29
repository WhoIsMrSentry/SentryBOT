from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Request
from typing import Any


def get_person_router(processor: Any, base_url: str) -> APIRouter:
    r = APIRouter(tags=["vlm-person"])

    @r.post("/person/remember", tags=["vision"], summary="Remember/store person with relationship")
    def remember_person(body: dict):
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

        if name and not person_id:
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

    @r.post("/memory/chat", tags=["memory"], summary="Append chat to person's memory")
    def memory_chat(person: str, text: str, role: str = "assistant"):
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

    @r.post("/faces/register", tags=["faces"], summary="Register current face with name")
    def register_face(name: str):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")

        if not processor.face_manager:
            raise HTTPException(status_code=501, detail="Face recognition not available")
        logger = logging.getLogger("vlm_bridge.api.router")

        try:
            success = processor.register_face_from_current_frame(name)
        except Exception as e:
            logger.debug("register_face primary attempt failed: %s", e)
            success = False

        if success:
            return {"status": "success", "message": f"Registered face for {name}"}

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
        if not processor or not processor.face_manager:
            return {"faces": []}
        return {"faces": processor.face_manager.known_face_names}

    return r
