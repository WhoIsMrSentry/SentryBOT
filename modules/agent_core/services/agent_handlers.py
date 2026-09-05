from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("agent.handlers")


def register_default_action_handlers(orchestrator: Any) -> None:
    """Bind ActionArbiter actions to concrete side effects for the orchestrator."""

    def _handle_speak(req):
        text = str(req.payload.get("text", "")).strip()
        if not text:
            return {"ok": False, "reason": "missing_text"}
        tone = req.payload.get("tone")
        if not isinstance(tone, (dict, str)) or tone == "":
            tone = None
        orchestrator.speech_arbiter.enqueue(
            text=text,
            priority=max(1, min(100, int(req.priority))),
            category="final" if req.priority >= 60 else "progress",
            language=str(req.payload.get("language", "") or ""),
            tone=tone,
        )
        return {"ok": True}

    def _http_post(path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            import requests  # type: ignore
        except Exception as exc:
            return {"ok": False, "reason": "no_requests", "error": str(exc)}
        url = f"{orchestrator._gateway_base_url}{path}"
        try:
            resp = requests.post(
                url,
                json=payload or {},
                timeout=orchestrator._action_http_timeout_s,
            )
            if resp.status_code != 200:
                return {"ok": False, "reason": "http_error", "status": resp.status_code}
            try:
                return {"ok": True, "data": resp.json()}
            except Exception:
                return {"ok": True, "data": {}}
        except Exception as exc:
            return {"ok": False, "reason": "http_exception", "error": str(exc)}

    def _handle_head(req):
        pan = orchestrator.safety_filter.clamp_servo(int(req.payload.get("pan", 90)))
        tilt = orchestrator.safety_filter.clamp_servo(int(req.payload.get("tilt", 90)))
        drive = int(req.payload.get("drive", 0) or 0)
        return _http_post(
            "/vlm/track",
            {"head_pan": pan, "head_tilt": tilt, "drive": drive},
        )

    def _handle_lights(req):
        if not orchestrator.autonomy_client:
            return {"ok": False, "reason": "no_client"}
        effect = str(req.payload.get("effect", "BREATHE"))
        color = req.payload.get("color")
        try:
            duration_ms = max(200, int(float(req.payload.get("duration_ms", 800) or 800)))
        except (TypeError, ValueError):
            duration_ms = 800
        ttl_s = duration_ms / 1000.0 + 0.3
        if not orchestrator.expression_arbiter.claim_lights(
            req.source,
            force=req.priority >= 90,
            priority=int(req.priority),
            ttl_s=ttl_s,
        ):
            return {"ok": False, "reason": "lights_locked"}
        return orchestrator.autonomy_client.set_neopixel(
            effect,
            color=color if isinstance(color, list) else None,
            lease_source=req.source,
        )

    def _handle_vision_query(req):
        question = str(req.payload.get("question", "")).strip()
        if not question:
            return {"ok": False, "reason": "missing_question"}
        return _http_post("/vlm/ask", {"question": question})

    def _handle_follow_owner(req):
        return _http_post("/vlm/follow/owner/start", {})

    def _handle_stop_follow(req):
        return _http_post("/vlm/follow/stop", {})

    def _handle_look_around(req):
        steps = req.payload.get("steps") if isinstance(req.payload, dict) else None
        if not isinstance(steps, list) or not steps:
            steps = [(60, 90), (90, 90), (120, 90), (90, 90)]
        last: Dict[str, Any] = {}
        for entry in steps:
            if isinstance(entry, dict):
                pan = entry.get("pan", 90)
                tilt = entry.get("tilt", 90)
            else:
                try:
                    pan, tilt = entry
                except Exception:
                    continue
            last = _http_post(
                "/vlm/track",
                {
                    "head_pan": orchestrator.safety_filter.clamp_servo(int(pan or 90)),
                    "head_tilt": orchestrator.safety_filter.clamp_servo(int(tilt or 90)),
                },
            )
        return last

    def _handle_face_focus(req):
        name = str(req.payload.get("name", "")).strip()
        if not name:
            return {"ok": False, "reason": "missing_name"}
        return _http_post("/vlm/focus/person", {"name": name})

    def _handle_face_register(req):
        name = str(req.payload.get("name", "")).strip()
        relationship = str(req.payload.get("relationship", "known")).strip() or "known"
        level = int(req.payload.get("recognition_level", 2) or 2)
        if not name:
            return {"ok": False, "reason": "missing_name"}
        return _http_post(
            "/vlm/person/remember",
            {"name": name, "relationship": relationship, "recognition_level": level},
        )


    def _handle_notification(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        event_type = str(payload.get("event_type", payload.get("type", "notification")) or "notification").strip().lower()
        silent = bool(payload.get("silent", False))

        default_messages = {
            "hazard_detected": "Dikkat, olasi bir tehlike algiladim.",
            "owner_follow_intent": "Seni takip etmeye hazirim.",
            "new_person_seen": "Yeni birini goruyorum.",
            "idle_comment_request": "Buradayim ve etrafi izliyorum.",
            "notification": "Bildirim alindi.",
        }

        text = str(
            payload.get("text")
            or payload.get("message")
            or payload.get("summary")
            or default_messages.get(event_type, default_messages["notification"])
        ).strip()

        progress_payload = {
            "type": event_type,
            "source": req.source,
            "priority": int(req.priority),
            "text": text,
            "payload": payload,
        }
        try:
            progress = getattr(orchestrator, "progress_manager", None)
            if progress is not None and hasattr(progress, "on_progress_event"):
                progress.on_progress_event(progress_payload)
        except Exception as exc:
            logger.debug("Notification progress hook failed: %s", exc)

        if not silent and text:
            try:
                orchestrator.speech_arbiter.enqueue(
                    text=text,
                    priority=max(1, min(100, int(req.priority))),
                    category="final" if req.priority >= 60 else "progress",
                    language=str(payload.get("language", "") or ""),
                    tone=payload.get("tone") if payload.get("tone") else None,
                )
                return {"ok": True, "event_type": event_type, "spoken": True, "text": text}
            except Exception as exc:
                return {"ok": False, "reason": "speech_enqueue_failed", "event_type": event_type, "error": str(exc)}

        return {"ok": True, "event_type": event_type, "spoken": False, "text": text}

    orchestrator.action_arbiter.register_handler("speak", _handle_speak)
    orchestrator.action_arbiter.register_handler("head_move", _handle_head)
    orchestrator.action_arbiter.register_handler("lights", _handle_lights)
    orchestrator.action_arbiter.register_handler("vision_query", _handle_vision_query)
    orchestrator.action_arbiter.register_handler("follow_owner", _handle_follow_owner)
    orchestrator.action_arbiter.register_handler("stop_follow", _handle_stop_follow)
    orchestrator.action_arbiter.register_handler("look_around", _handle_look_around)
    orchestrator.action_arbiter.register_handler("face_focus", _handle_face_focus)
    orchestrator.action_arbiter.register_handler("face_register", _handle_face_register)
    orchestrator.action_arbiter.register_handler("notification", _handle_notification)
