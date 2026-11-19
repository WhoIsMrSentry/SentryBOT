from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from modules.arduino_serial.contract import (
    build_buzzer_cmd,
    build_cute_cmd,
    build_drive_cmd,
    build_laser_cmd,
    build_simple_cmd,
    build_stepper_cmd,
)

logger = logging.getLogger("agent.handlers")


def register_default_action_handlers(orchestrator: Any) -> None:
    """Bind ActionArbiter actions to concrete side effects for the orchestrator."""
    try:
        import requests  # type: ignore

        session = requests.Session()
        orchestrator._handler_http_session = session
    except Exception:
        requests = None  # type: ignore
        session = None

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
            voice=str(req.payload.get("voice", "") or ""),
        )
        return {"ok": True}

    def _http_post(path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if requests is None and session is None:
            return {"ok": False, "reason": "no_requests"}
        url = f"{orchestrator._gateway_base_url}{path}"
        try:
            post_fn = getattr(requests, "post", None)
            if post_fn is not None and getattr(post_fn, "__module__", "") != "requests.api":
                resp = post_fn(
                    url,
                    json=payload or {},
                    timeout=orchestrator._action_http_timeout_s,
                )
            elif session is not None:
                resp = session.post(
                    url,
                    json=payload or {},
                    timeout=orchestrator._action_http_timeout_s,
                )
            else:
                return {"ok": False, "reason": "no_requests"}
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

    def _handle_express(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        mods = payload.get("modalities") or ["leds", "oled", "voice", "head"]
        if "leds" in mods and getattr(orchestrator, "expression_arbiter", None) is not None:
            try:
                dur = min(30.0, max(0.5, float(payload.get("duration_s", 3.0) or 3.0)))
            except (TypeError, ValueError):
                dur = 3.0
            if not orchestrator.expression_arbiter.claim_lights(
                req.source,
                force=req.priority >= 90,
                priority=int(req.priority),
                ttl_s=dur + 0.3,
            ):
                return {"ok": False, "reason": "lights_locked"}
        return _http_post("/expression/express", payload)

    def _arduino_exec(payload: Dict[str, Any], timeout_s: float = 1.2) -> Dict[str, Any]:
        cli = getattr(orchestrator, "autonomy_client", None)
        if cli is not None and hasattr(cli, "arduino_request"):
            resp = cli.arduino_request(payload, timeout=timeout_s)
            if isinstance(resp, dict):
                return {"ok": bool(resp.get("ok", True)), "resp": resp}
            return {"ok": bool(resp is not None), "resp": resp}
        data = _http_post("/arduino/request", payload)
        return data

    _laser_off_timer_lock = threading.Lock()
    _laser_off_timer: list[Optional[threading.Timer]] = [None]

    def _cancel_laser_timer() -> None:
        with _laser_off_timer_lock:
            t = _laser_off_timer[0]
            if t is not None:
                t.cancel()
                _laser_off_timer[0] = None

    def _handle_legs_posture(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        posture = str(payload.get("posture") or "stand").strip().lower()
        if posture not in {"stand", "sit", "home", "estop", "calibrate", "zero_now"}:
            return {"ok": False, "reason": "invalid_posture"}
        return _arduino_exec(build_simple_cmd(posture), timeout_s=1.5)

    def _handle_legs_move(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        direction = str(payload.get("direction") or "stop").strip().lower()
        if direction == "stop":
            return _arduino_exec(build_simple_cmd("estop"), timeout_s=1.0)
        raw_speed = int(payload.get("speed", 60) or 60)
        safe_speed = abs(int(orchestrator.safety_filter.clamp_stepper(raw_speed)))
        if safe_speed == 0:
            return _arduino_exec(build_drive_cmd(0), timeout_s=1.0)
        if direction == "forward":
            return _arduino_exec(build_drive_cmd(safe_speed), timeout_s=1.2)
        if direction == "backward":
            return _arduino_exec(build_drive_cmd(-safe_speed), timeout_s=1.2)
        if direction in {"left", "right"}:
            sign = 1 if direction == "right" else -1
            steps = max(20, min(2000, int(payload.get("steps", 200) or 200)))
            r0 = _arduino_exec(build_stepper_cmd(0, "pos", sign * steps, drive=safe_speed), timeout_s=1.2)
            r1 = _arduino_exec(build_stepper_cmd(1, "pos", -sign * steps, drive=safe_speed), timeout_s=1.2)
            return {"ok": bool(r0.get("ok") and r1.get("ok")), "left": r0, "right": r1}
        return {"ok": False, "reason": "invalid_direction"}

    def _handle_laser(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        on = bool(payload.get("on", False))
        target = str(payload.get("target") or "both").strip().lower()
        _cancel_laser_timer()
        if not on or target == "off":
            return _arduino_exec(build_laser_cmd(on=False, both=True), timeout_s=1.0)
        duration_s = float(orchestrator.safety_filter.clamp_laser_duration(float(payload.get("duration_s", 2.0) or 2.0)))
        if target in {"1", "left"}:
            cmd = build_laser_cmd(on=True, id_=1)
        elif target in {"2", "right"}:
            cmd = build_laser_cmd(on=True, id_=2)
        else:
            cmd = build_laser_cmd(on=True, both=True)
        res = _arduino_exec(cmd, timeout_s=1.0)
        if duration_s > 0.05:
            def _auto_off() -> None:
                try:
                    _arduino_exec(build_laser_cmd(on=False, both=True), timeout_s=1.0)
                except Exception:
                    pass
            timer = threading.Timer(duration_s, _auto_off)
            timer.daemon = True
            with _laser_off_timer_lock:
                _laser_off_timer[0] = timer
            timer.start()
        return res

    def _handle_ears(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        gesture = str(payload.get("gesture") or "").strip().lower()
        cli = getattr(orchestrator, "autonomy_client", None)
        if gesture:
            if cli is not None and hasattr(cli, "ear_gesture"):
                return cli.ear_gesture(gesture) or {"ok": False}
            return _http_post(f"/piservo/gesture?name={gesture}", {})
        left = payload.get("left")
        right = payload.get("right")
        l_deg = orchestrator.safety_filter.clamp_servo(int(left if left is not None else 90))
        r_deg = orchestrator.safety_filter.clamp_servo(int(right if right is not None else 90))
        if cli is not None and hasattr(cli, "set_ears"):
            return cli.set_ears(l_deg, r_deg) or {"ok": False}
        return _http_post(f"/piservo/set?left={l_deg}&right={r_deg}", {})

    def _handle_piservo_reflex(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        angle = float(payload.get("angle", 0.0) or 0.0)
        energy = float(payload.get("energy", 1.0) or 1.0)
        cli = getattr(orchestrator, "autonomy_client", None)
        if cli is not None and hasattr(cli, "ear_reflex"):
            return cli.ear_reflex(angle, energy=energy) or {"ok": False}
        return _http_post(f"/piservo/reflex?angle={angle}&energy={energy}", {})

    def _handle_audio_hw(req):
        payload = req.payload if isinstance(req.payload, dict) else {}
        cute_name = str(payload.get("cute_sound") or "").strip()
        if cute_name:
            return _arduino_exec(build_cute_cmd(cute_name), timeout_s=1.2)
        freq = max(100, min(10000, int(payload.get("frequency", 2200) or 2200)))
        ms = max(10, min(2000, int(payload.get("duration_ms", 80) or 80)))
        return _arduino_exec(build_buzzer_cmd(freq=freq, ms=ms), timeout_s=1.0)

    orchestrator.action_arbiter.register_handler("speak", _handle_speak)
    orchestrator.action_arbiter.register_handler("express", _handle_express)
    orchestrator.action_arbiter.register_handler("head_move", _handle_head)
    orchestrator.action_arbiter.register_handler("lights", _handle_lights)
    orchestrator.action_arbiter.register_handler("legs_posture", _handle_legs_posture)
    orchestrator.action_arbiter.register_handler("legs_move", _handle_legs_move)
    orchestrator.action_arbiter.register_handler("laser", _handle_laser)
    orchestrator.action_arbiter.register_handler("ears", _handle_ears)
    orchestrator.action_arbiter.register_handler("piservo_reflex", _handle_piservo_reflex)
    orchestrator.action_arbiter.register_handler("audio_hw", _handle_audio_hw)
    orchestrator.action_arbiter.register_handler("vision_query", _handle_vision_query)
    orchestrator.action_arbiter.register_handler("follow_owner", _handle_follow_owner)
    orchestrator.action_arbiter.register_handler("stop_follow", _handle_stop_follow)
    orchestrator.action_arbiter.register_handler("look_around", _handle_look_around)
    orchestrator.action_arbiter.register_handler("face_focus", _handle_face_focus)
    orchestrator.action_arbiter.register_handler("face_register", _handle_face_register)
    orchestrator.action_arbiter.register_handler("notification", _handle_notification)
