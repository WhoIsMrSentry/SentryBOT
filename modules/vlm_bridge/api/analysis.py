from __future__ import annotations
from fastapi import APIRouter, HTTPException
from typing import Any


def get_analysis_router(processor: Any, base_url: str) -> APIRouter:
    r = APIRouter(tags=["vlm-analysis"])

    @r.post("/ask", tags=["vision"], summary="Ask the VLM a question about the current scene")
    def ask_vlm(body: dict):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")

        question = body.get("question", "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="question required")
        if not processor.is_local_camera_available():
            return {"ok": False, "answer": "Kamera görüntüsü şu an kullanılamıyor.", "reason": "camera_unavailable"}

        frame = None
        with processor._frame_lock:
            if processor._latest_raw_frame is not None:
                frame = processor._latest_raw_frame.copy()

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
            return {"ok": False, "answer": "Kamera görüntüsü alınamadı.", "reason": "no_frame"}

        if processor.vlm_client:
            try:
                answer = processor.vlm_client.ask_about_scene(frame, question, force=True)
                if answer:
                    if hasattr(processor, "refresh_visual_context"):
                        processor.refresh_visual_context(question=question)
                    return {"ok": True, "answer": answer}
            except Exception:
                pass

        return {"ok": False, "answer": "VLM sistemi şu an kullanılamıyor.", "reason": "vlm_unavailable"}

    @r.post("/analyze", tags=["analysis"], summary="Analyze single frame (local)")
    def analyze_snapshot():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not processor.is_local_camera_available():
            raise HTTPException(status_code=503, detail="camera_unavailable")
        results = processor.analyze_snapshot()
        return {"results": results}

    @r.post("/ocr", tags=["analysis"], summary="Run OCR on current frame via remote multimodal server")
    def ocr_endpoint(body: dict | None = None):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "run_ocr_remote"):
            raise HTTPException(status_code=501, detail="OCR proxy not available")
        body = body or {}
        languages = body.get("languages") if isinstance(body, dict) else None
        if isinstance(languages, (list, tuple)):
            languages = [str(x).strip() for x in languages if str(x).strip()]
        else:
            languages = None
        return processor.run_ocr_remote(frame=None, languages=languages)

    @r.post("/fer/analyze", tags=["vision"], summary="Face emotion from base64 JPEG (DeepFace or heuristic)")
    def fer_analyze(body: dict):
        image_b64 = str(body.get("image_b64") or "").strip()
        if not image_b64:
            raise HTTPException(status_code=400, detail="image_b64 required")
        try:
            import base64
            import cv2
            import numpy as np

            raw = base64.b64decode(image_b64)
            arr = np.frombuffer(raw, dtype=np.uint8)
            face = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if face is None:
                return {"ok": False, "emotion": "neutral", "confidence": 0.0}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "emotion": "neutral", "confidence": 0.0}

        # Optional DeepFace when installed on the robot.
        try:
            from deepface import DeepFace  # type: ignore

            result = DeepFace.analyze(face, actions=["emotion"], enforce_detection=False)
            if isinstance(result, list) and result:
                result = result[0]
            emo_map = result.get("emotion") if isinstance(result, dict) else {}
            if isinstance(emo_map, dict) and emo_map:
                label = max(emo_map, key=emo_map.get)
                conf = float(emo_map.get(label, 0.0)) / 100.0
                return {"ok": True, "emotion": str(label).lower(), "confidence": round(conf, 3), "backend": "deepface"}
        except Exception:
            pass

        if processor is not None and getattr(processor, "_face_emotion", None) is not None:
            out = processor._face_emotion.estimate(face)
            out["ok"] = True
            return out

        return {"ok": True, "emotion": "neutral", "confidence": 0.0, "backend": "none"}

    return r
