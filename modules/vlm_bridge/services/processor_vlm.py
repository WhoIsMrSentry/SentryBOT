from __future__ import annotations

import base64
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
import requests

try:
    from .vision_event_bus import (
        EVENT_SCENE_CHANGED,
        EVENT_VLM_RESULT_READY,
    )
except Exception:
    EVENT_SCENE_CHANGED = "scene_changed"
    EVENT_VLM_RESULT_READY = "vlm_result_ready"

from .processor_vlm_signals import ProcessorVlmSignalsMixin

logger = logging.getLogger("vlm_bridge.vlm")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProcessorVlmMixin(ProcessorVlmSignalsMixin):
    """VLM query, multimodal API calls, sampling, and visual context cache logic."""

    def _vlm_refresh_lock_obj(self):
        lock = getattr(self, "_vlm_refresh_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._vlm_refresh_lock = lock
        return lock

    def _try_begin_vlm_refresh(self) -> bool:
        with self._vlm_refresh_lock_obj():
            if bool(getattr(self, "_vlm_refresh_inflight", False)):
                return False
            self._vlm_refresh_inflight = True
            return True

    def _finish_vlm_refresh(self) -> None:
        with self._vlm_refresh_lock_obj():
            self._vlm_refresh_inflight = False

    visual_context_cache: Optional[Any]
    _context_max_age_s: float
    latest_results: List[Dict[str, Any]]
    vision_semantic_budget: Dict[str, Any]
    vision_request_gate: Optional[Any]
    vision_sampler: Optional[Any]
    _frame_lock: threading.Lock
    _latest_raw_frame: Optional[Any]
    remote_mm_enabled: bool
    remote_mm_endpoint: str
    remote_mm_cheap_endpoint: str
    remote_mm_semantic_endpoint: str
    remote_mm_timeout_s: float
    remote_mm_auth_token: str
    mode_categories: Dict[str, Dict[str, bool]]
    mode_flags: Dict[str, bool]
    vlm_client: Optional[Any]
    event_bus: Optional[Any]
    camera_source: Any

    def _maybe_sample_vlm(self, parsed_results: List[Dict[str, Any]]) -> None:
        sampler = getattr(self, "vision_sampler", None)
        if sampler is None:
            return
        if getattr(self, "_vlm_refresh_inflight", False):
            return
        score = self._scene_change_score(parsed_results)
        owner_seen, new_person = self._person_signals(parsed_results)
        hazard = self._hazard_signal(parsed_results)
        sudden_motion = score >= max(getattr(self, "_sudden_motion_threshold", 0.7), sampler.scene_change_threshold + 0.25)
        is_bored = bool(getattr(self, "_is_bored", False))
        try:
            should = sampler.should_call_vlm(
                scene_change_score=score,
                follow_mode_active=bool(getattr(self, "_follow_active", False)),
                owner_seen=owner_seen,
                new_person=new_person,
                hazard_detected=hazard,
                sudden_motion=sudden_motion,
                is_bored=is_bored,
            )
        except Exception:
            return
        if not should:
            return

        if not self._try_begin_vlm_refresh():
            return

        reason, priority = self._vlm_reason_from_signals(
            score=score,
            owner_seen=owner_seen,
            new_person=new_person,
            hazard=hazard,
            sudden_motion=sudden_motion,
            is_bored=is_bored,
        )
        request_id = ""
        gate = getattr(self, "vision_request_gate", None)
        if gate is not None:
            has_cache, cache_age_s = self._visual_context_cache_state()
            try:
                decision = gate.decide(
                    reason=reason,
                    priority=priority,
                    scene_key=self._vlm_scene_key(parsed_results),
                    force=False,
                    has_cache=has_cache,
                    cache_age_s=cache_age_s,
                )
            except Exception as exc:
                logger.debug("VLM gate decision failed: %s", exc)
                decision = None
            if decision is not None and not decision.allowed:
                logger.debug(
                    "VLM gate skipped reason=%s mode=%s wait_s=%.1f use_cache=%s",
                    decision.reason,
                    decision.mode,
                    float(decision.wait_s or 0.0),
                    bool(decision.use_cache),
                )
                self._finish_vlm_refresh()
                return
            if decision is not None:
                request_id = decision.request_id
                try:
                    gate.mark_start(request_id, reason=reason, priority=priority)
                except Exception:
                    pass
                logger.info("VLM gate approved reason=%s priority=%s request_id=%s", reason, priority, request_id)

        sampler.record_call()
        try:
            threading.Thread(target=self._background_context_refresh, args=(reason, request_id), daemon=True).start()
        except Exception:
            self._finish_vlm_refresh()
            raise

    def _background_context_refresh(self, reason: str = "background_refresh", request_id: str = "") -> None:
        ok = False
        try:
            try:
                context = self.refresh_visual_context(semantic_reason=reason, semantic_request_id=request_id)
            except TypeError:
                context = self.refresh_visual_context()
            ok = context is not None
            if context is not None and self.event_bus is not None:
                self.event_bus.publish(EVENT_SCENE_CHANGED, {"context": context, "reason": reason})
                self.event_bus.publish(EVENT_VLM_RESULT_READY, {"context": context, "reason": reason})
        except Exception as exc:
            logger.debug("VLM background context refresh failed: %s", exc)
        finally:
            gate = getattr(self, "vision_request_gate", None)
            if gate is not None and request_id:
                try:
                    gate.mark_finish(request_id, ok=ok)
                except Exception:
                    pass
            self._finish_vlm_refresh()

    def _call_remote_multimodal(
        self,
        frame: Any,
        *,
        run_semantic_vlm: bool = False,
        semantic_reason: str = "",
        request_id: str = "",
        question: str = "",
    ) -> Optional[Dict[str, Any]]:
        if not self.remote_mm_enabled or not self.remote_mm_endpoint:
            return None
        endpoint = self._remote_multimodal_endpoint_for(bool(run_semantic_vlm))
        if not endpoint:
            return None
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                return None
            image_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            payload: Dict[str, Any] = {
                "image_b64": image_b64,
                "run_semantic_vlm": bool(run_semantic_vlm),
                "semantic_reason": str(semantic_reason or ""),
                "request_id": str(request_id or ""),
                "question": str(question or ""),
                "mode": "semantic" if bool(run_semantic_vlm) else "cheap",
            }
            requested = self._remote_requested_tasks(run_semantic_vlm=bool(run_semantic_vlm))
            if requested:
                payload["requested_tasks"] = requested
            headers = {}
            if self.remote_mm_auth_token:
                headers["X-Auth-Token"] = self.remote_mm_auth_token
            resp = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self.remote_mm_timeout_s,
            )
            if resp.status_code in (404, 405) and endpoint != self.remote_mm_endpoint:
                resp = requests.post(
                    self.remote_mm_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.remote_mm_timeout_s,
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.debug("remote multimodal call failed: %s", exc)
        return None

    def _context_from_remote_multimodal(self, mm: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        people = list(mm.get("people", []) or [])
        objects = list(mm.get("objects", []) or [])
        hazards = list(mm.get("hazards", []) or [])
        summary = str(mm.get("summary", "")).strip()
        interpretation = str(mm.get("persona_interpretation", "")).strip() or summary
        importance = float(mm.get("importance_score", 0.55 if hazards else 0.4))
        return {
            "timestamp": _utc_iso(),
            "summary": summary,
            "objects": objects,
            "people": people,
            "hazards": hazards,
            "interesting_events": list(mm.get("interesting_events", []) or []),
            "recommended_focus": dict(mm.get("recommended_focus", {}) or {}),
            "importance_score": min(1.0, max(0.0, importance + (0.1 if question else 0.0))),
            "raw_vlm_observation": str(mm.get("raw_text", "")),
            "persona_interpretation": interpretation,
        }

    def get_latest_visual_context(self) -> Optional[Dict[str, Any]]:
        if self.visual_context_cache is None:
            return None
        if self.visual_context_cache.age_s > self._context_max_age_s:
            return None
        ctx = self.visual_context_cache.get_latest()
        if ctx is None:
            compatibility_context = self._build_context_from_results(self.latest_results)
            if compatibility_context is None:
                return None
            self.update_visual_context(compatibility_context)
            ctx = self.visual_context_cache.get_latest()
            if ctx is None:
                return None
        return ctx.to_dict()

    def refresh_visual_context(
        self,
        question: str = "",
        *,
        semantic_reason: str = "",
        semantic_request_id: str = "",
        force_semantic: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        semantic_reason = "user_question" if str(question or "").strip() else (semantic_reason or "manual_refresh")
        run_semantic_vlm = self._semantic_budget_allows(
            question=question,
            reason=semantic_reason,
            force=force_semantic,
        )
        if bool((getattr(self, "vision_semantic_budget", {}) or {}).get("log_decisions", True)):
            logger.info(
                "VLM semantic budget reason=%s run=%s request_id=%s",
                semantic_reason,
                bool(run_semantic_vlm),
                semantic_request_id or "-",
            )
        frame = None
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                frame = self._latest_raw_frame.copy()

        if frame is not None and self.remote_mm_enabled:
            mm_result = self._call_remote_multimodal(frame)
            if isinstance(mm_result, dict) and mm_result.get("ok", True):
                context = self._context_from_remote_multimodal(mm_result, question=question)
                self.update_visual_context(context)
                merged_results = []
                for p in context.get("people", []):
                    if isinstance(p, dict):
                        merged_results.append(
                            {
                                "label": "person",
                                "name": p.get("name", "Unknown"),
                                "confidence": float(p.get("confidence", 0.0) or 0.0),
                                "bbox": p.get("bbox", []),
                                "distance_m": p.get("distance_m"),
                            }
                        )
                for o in context.get("objects", []):
                    if isinstance(o, dict):
                        merged_results.append(o)
                if merged_results:
                    self.latest_results = merged_results
                latest = self.get_latest_visual_context()
                if latest is not None:
                    return latest

        if frame is not None and self.vlm_client is not None and run_semantic_vlm:
            vlm_result = self.vlm_client.analyze_frame(frame, force=bool(question))
            if isinstance(vlm_result, dict):
                context = {
                    "timestamp": _utc_iso(),
                    "summary": str(vlm_result.get("summary", "")),
                    "objects": list(vlm_result.get("objects", []) or []),
                    "people": list(vlm_result.get("people", []) or []),
                    "hazards": list(vlm_result.get("hazards", []) or []),
                    "interesting_events": list(vlm_result.get("interesting", []) or vlm_result.get("interesting_events", []) or []),
                    "recommended_focus": dict(vlm_result.get("recommended_focus", {}) or {}),
                    "importance_score": 0.6 if question else 0.4,
                    "raw_vlm_observation": str(vlm_result.get("raw_text", "")),
                    "persona_interpretation": str(vlm_result.get("summary", "")),
                }
                self.update_visual_context(context, is_user_question=bool(question))
                latest = self.get_latest_visual_context()
                if latest is not None:
                    return latest

        compatibility_context = self._build_context_from_results(self.latest_results)
        if compatibility_context is not None:
            self.update_visual_context(compatibility_context, is_user_question=bool(question))
            return self.get_latest_visual_context()
        return None

    def _build_context_from_results(self, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not results:
            return None
        people = []
        objects = []
        for item in results:
            if str(item.get("label", "")).lower() == "person":
                people.append(
                    {
                        "track_id": "",
                        "person_id": "",
                        "name": item.get("name", "Unknown"),
                        "recognition_level": 0 if item.get("name", "Unknown") == "Unknown" else 2,
                        "relationship": "unknown",
                        "confidence": float(item.get("confidence", 0.0) or 0.0),
                        "bbox": list(item.get("bbox", [0, 0, 0, 0])),
                        "distance_m": item.get("distance_m"),
                        "gaze_priority": 0.4,
                        "last_seen": _utc_iso(),
                        "is_follow_target": bool(item.get("tracked", False)),
                        "appearance_notes": "",
                        "emotion": str(item.get("emotion", "") or "").strip(),
                    }
                )
            else:
                objects.append(item)
        summary = f"{len(people)} kişi ve {len(objects)} nesne algılandı."
        return {
            "timestamp": _utc_iso(),
            "summary": summary,
            "objects": objects,
            "people": people,
            "hazards": [],
            "interesting_events": [],
            "recommended_focus": {"type": "person" if people else "none", "target_id": "", "reason": "latest_detection"},
            "importance_score": 0.5 if people else 0.3,
            "raw_vlm_observation": summary,
            "persona_interpretation": summary,
        }

    def update_visual_context(
        self,
        context: Optional[Dict[str, Any]],
        *,
        is_user_question: bool = False,
        is_scene_change: bool = True,
    ) -> None:
        if self.visual_context_cache is None or context is None:
            return
        try:
            if hasattr(self.visual_context_cache, "set_context"):
                self.visual_context_cache.set_context(context)
            else:
                from .visual_context import PersonContext, VisionFrameContext, compute_importance

                vfc = VisionFrameContext(
                    timestamp=context.get("timestamp", ""),
                    summary=context.get("summary", ""),
                    objects=context.get("objects", []),
                    people=[PersonContext(**p) if isinstance(p, dict) else p for p in context.get("people", [])],
                    hazards=context.get("hazards", []),
                    interesting_events=context.get("interesting_events", []),
                    recommended_focus=context.get("recommended_focus", {}),
                    importance_score=context.get("importance_score", 0.0),
                    raw_vlm_observation=context.get("raw_vlm_observation", ""),
                    persona_interpretation=context.get("persona_interpretation", ""),
                )
                prev_id = getattr(self.visual_context_cache, "previous_scene_id", "")
                derived = compute_importance(
                    vfc,
                    is_user_question=is_user_question,
                    is_scene_change=is_scene_change,
                    is_follow_active=bool(getattr(self, "_follow_active", False)),
                    previous_scene_id=prev_id,
                )
                vfc.importance_score = max(float(context.get("importance_score", 0.0) or 0.0), derived)
                context["importance_score"] = vfc.importance_score
                self.visual_context_cache.update(vfc)
        except Exception as exc:
            logger.debug("Failed to update visual context: %s", exc)
