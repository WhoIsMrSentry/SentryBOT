"""Owner presence, authority guard, and session tracking logic."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger("autonomy.owner_guard")


class OwnerGuardMixin:
    """Encapsulates owner scanning, permissions, session tracking, and request throttling."""

    def _maybe_scan_for_owner(self) -> None:
        if not self.owner_cfg.get("enabled"):
            return
        if self._has_full_owner_authority():
            return
        now = time.time()
        interval = self.owner_cfg.get("scan_interval_s", 25)
        if now - self._last_owner_scan < interval:
            return
        self._last_owner_scan = now
        self.client.push_interaction_event("owner.scan")
        if not self._trigger_animation("owner_scan"):
            self._perform_owner_scan()

    def _refresh_rfid_authorization(self) -> None:
        rfid_cfg = self.owner_cfg.get("rfid", {})
        endpoint = rfid_cfg.get("endpoint")
        if not endpoint:
            return
        now = time.time()
        poll_interval_s = float(rfid_cfg.get("poll_interval_s", 5.0))
        last_check = float(self.state.get("rfid_last_check", 0.0) or 0.0)
        if poll_interval_s > 0 and (now - last_check) < poll_interval_s:
            return
        self.state["rfid_last_check"] = now
        if self._owner_seen_recently():
            return
        if self._rfid_active():
            return
        if self.client.check_rfid(endpoint):
            grace = rfid_cfg.get("grace_s", 120)
            self.state["rfid_authorized_until"] = time.time() + grace
            self.client.push_interaction_event("owner.rfid")
            self.memory.add_event("RFID ile yetkilendirildi.")

    def _address_owner(self, style: str = "formal") -> str:
        mapping = self.owner_cfg.get("addressing", {})
        fallback = self.owner_cfg.get("name", "Sahibim")
        return mapping.get(style) or mapping.get("formal") or fallback

    def _features_locked_for_request(self, text: str) -> bool:
        if not text:
            return False
        if self._has_full_owner_authority():
            return False
        keywords = self.owner_cfg.get("restricted_keywords") or []
        lowered = text.lower()
        if any(k.lower() in lowered for k in keywords if k):
            alias = self._address_owner("affectionate")
            message = f"{alias} yokken bunu yapamam."
            self._speak_with_mood(message, emotion="fear")
            self.client.push_interaction_event("owner.locked")
            self.memory.add_event(f"Blocked sensitive request: {text}")
            return True
        return False

    def _handle_owner_commands(self, text: str, speaker: str | None) -> bool:
        return False

    def _owner_guard_enabled(self) -> bool:
        return bool(self.owner_cfg.get("enabled") and self.owner_cfg.get("require_presence", True))

    def _owner_seen_recently(self) -> bool:
        if not self.owner_cfg.get("enabled"):
            return True
        timeout = self.owner_cfg.get("presence_timeout_s", 30)
        last = self.state.get("owner_last_seen", 0.0)
        return (time.time() - last) <= timeout

    def _owner_cooldown_active(self) -> bool:
        return time.time() < self.state.get("owner_lockout_until", 0.0)

    def _rfid_active(self) -> bool:
        return time.time() < self.state.get("rfid_authorized_until", 0.0)

    def _has_full_owner_authority(self) -> bool:
        if not self.owner_cfg.get("enabled"):
            return True
        return any([
            self._owner_seen_recently(),
            self._rfid_active(),
        ])

    def _maybe_block_request(self, text: str) -> tuple[str, str] | None:
        if not self._owner_guard_enabled():
            return None
        if self._has_full_owner_authority():
            return None
        entry = self._record_external_request(text)
        affectionate = self._address_owner("affectionate")
        if self._owner_cooldown_active():
            msg = self.owner_cfg.get("cooldown_message", "Sahibim gelene kadar konuşmak istemiyorum.")
            return (msg.replace("{nickname}", affectionate), "fear")
        threshold = self.owner_cfg.get("max_requests_without_owner", 3)
        if entry["recent_count"] >= threshold:
            self.state["owner_lockout_until"] = time.time() + self.owner_cfg.get("cooldown_s", 20)
            entry["angered"] = True
            self.client.push_interaction_event("autonomy.angry")
            if hasattr(self, "appraise_event"):
                self.appraise_event("owner_lockout")
            else:
                self.mood.modify("happiness", -10)
                self.mood.modify("fear", 15)
            msg = self.owner_cfg.get("angry_message", "Yeter artık! Sahibim olmadan seni dinlemeyeceğim.")
            return (msg.replace("{nickname}", affectionate), "fear")
        msg = self.owner_cfg.get("polite_message", "Sahibim olmadan isteğini yerine getiremiyorum.")
        return (msg.replace("{nickname}", affectionate), "neutral")

    def _record_external_request(self, text: str) -> Dict[str, Any]:
        if not hasattr(self, "_attempt_log"):
            self._attempt_log = []
        now = time.time()
        person = self._guess_active_person() or "Unknown"
        entry = {
            "timestamp": now,
            "person": person,
            "text": text,
            "angered": False,
            "recent_count": 1,
        }
        self._attempt_log.append(entry)
        if len(self._attempt_log) > 50:
            self._attempt_log = self._attempt_log[-50:]
        window = self.owner_cfg.get("speaker_window_s", 10)
        same_person = [a for a in self._attempt_log if a["person"] == person and now - a["timestamp"] <= window]
        entry["recent_count"] = len(same_person)
        self._owner_report_pending = True
        return entry

    def _guess_active_person(self) -> str | None:
        if not getattr(self, "_current_people", None):
            return None
        now = time.time()
        window = self.owner_cfg.get("speaker_window_s", 10)
        candidates = [(name, ts) for name, ts in self._current_people.items() if now - ts <= window]
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[1], reverse=True)
        for name, _ in candidates:
            if not self._is_owner_name(name):
                return name
        return candidates[0][0]

    def _is_owner_name(self, name: str | None) -> bool:
        if not name or name == "Unknown":
            return False
        owner_name = self.owner_cfg.get("name")
        aliases = self.owner_cfg.get("aliases") or []
        names = []
        if owner_name:
            names.append(owner_name)
        for a in aliases:
            if a:
                names.append(a)
        lowered = name.lower()
        for n in names:
            if n and lowered == n.lower():
                return True
        # Check person memory / social database for owner relationship
        try:
            record = self.client.get_person_memory(name)
            if record:
                p_data = record.get("record") or {}
                rel = str(p_data.get("relationship", "")).lower()
                lvl = int(p_data.get("recognition_level", 0) or 0)
                if rel == "owner" or lvl >= 5:
                    return True
        except Exception:
            pass
        return False

    def _on_owner_seen(self, timestamp: float) -> None:
        self.state["owner_last_seen"] = timestamp
        self.state["owner_lockout_until"] = 0.0
        self.state["rfid_authorized_until"] = 0.0
        affectionate = self._address_owner("affectionate")
        greet_cooldown = max(8, self.owner_cfg.get("presence_timeout_s", 25) / 2)
        if timestamp - self.state.get("owner_last_greet", 0.0) > greet_cooldown:
            # 1. Neopixel celebration effect (Rainbow / Pulse)
            try:
                self.client.set_interaction_effect("RAINBOW", duration_ms=2500, force=True)
            except Exception:
                pass
            # 2. OLED Face expression: Happy / Love
            try:
                self.client.apply_oled_face(mode="animation", name="love")
            except Exception:
                pass
            # 3. Servo head nod / happy animation
            try:
                self._trigger_animation("owner_scan")
            except Exception:
                pass

            greeting = self.owner_cfg.get("greeting", "Hoş geldin {name}! Geldiğine çok sevindim.")
            display_name = self.owner_cfg.get("name") or "Emir"
            if "{nickname}" in greeting:
                greeting = greeting.replace("{nickname}", affectionate)
            if "{name}" in greeting:
                greeting = greeting.replace("{name}", display_name)

            ran = self._run_scene(
                "owner_return",
                context={"name": display_name, "nickname": affectionate},
            )
            if not ran:
                self._speak_with_mood(greeting, emotion="joy")
            self.state["owner_last_greet"] = timestamp
        self.appraise_event("owner_returned")
        self._report_attempts_to_owner()

    def _report_attempts_to_owner(self) -> None:
        if not self._owner_report_pending or not self._attempt_log:
            return
        summary = self._compose_owner_report()
        if summary:
            affectionate = self._address_owner("affectionate")
            self._speak_with_mood(summary.replace("{nickname}", affectionate), emotion="joy")
        self._attempt_log.clear()
        self._owner_report_pending = False

    def _compose_owner_report(self) -> str | None:
        stats: Dict[str, Dict[str, Any]] = {}
        for entry in self._attempt_log:
            person = entry.get("person", "Unknown")
            data = stats.setdefault(person, {"count": 0, "examples": [], "angered": False})
            data["count"] += 1
            if len(data["examples"]) < 2:
                data["examples"].append(entry.get("text", ""))
            data["angered"] = data["angered"] or entry.get("angered", False)
        if not stats:
            return None
        fragments: list[str] = []
        for person, data in stats.items():
            base = f"{person} benden {data['count']} kez bir şey istedi"
            if data["examples"]:
                base += f" (örnek: '{data['examples'][0]}')"
            if data["angered"]:
                base += " ve beni sinirlendirdi"
            fragments.append(base)
        alias = self._address_owner("handle")
        return f"{alias}, " + "; ".join(fragments) + "."

    def _check_owner_presence_appraisal(self, now: float) -> None:
        if not self.owner_cfg.get("enabled"):
            return
        present = self._owner_seen_recently()
        self._sync_owner_session(present)
        if getattr(self, "_owner_was_present", False) and not present:
            last = float(self.state.get("owner_last_seen", 0.0) or 0.0)
            timeout = float(self.owner_cfg.get("presence_timeout_s", 30))
            if last > 0 and (now - last) >= timeout:
                if (now - getattr(self, "_last_owner_left_appraisal_ts", 0.0)) >= max(60.0, timeout):
                    self.appraise_event("owner_left")
                    self._last_owner_left_appraisal_ts = now
        self._owner_was_present = present

    def _owner_sessions_cfg(self) -> Dict[str, Any]:
        companion = self.config.get("companion", {}) if isinstance(self.config.get("companion"), dict) else {}
        cfg = companion.get("owner_sessions", {})
        return cfg if isinstance(cfg, dict) else {}

    def _social_db(self):
        return getattr(self.mood, "_social_db", None)

    def _sync_owner_session(self, owner_present: bool) -> None:
        cfg = self._owner_sessions_cfg()
        if not cfg.get("enabled", True):
            return
        db = self._social_db()
        if db is None:
            return
        source = str(cfg.get("source", "vision") or "vision")
        try:
            if owner_present:
                active = db.owner_sessions.active()
                if active is None:
                    self._owner_session_id = int(db.owner_sessions.start(source=source))
                else:
                    self._owner_session_id = int(active.get("id") or 0) or None
            elif getattr(self, "_owner_session_id", None) is not None:
                db.owner_sessions.end(self._owner_session_id)
                self._owner_session_id = None
            elif db.owner_sessions.active() is not None:
                db.owner_sessions.end_active()
        except Exception as exc:
            logger.debug("owner session sync failed: %s", exc)

    def _owner_absence_seconds(self, now: float) -> float:
        db = self._social_db()
        if db is not None:
            try:
                rows = db.owner_sessions.recent(limit=2)
                for row in rows:
                    end_ts = row.get("end_ts")
                    if end_ts:
                        return max(0.0, now - float(end_ts))
            except Exception:
                pass
        last = float(self.state.get("owner_last_seen", 0.0) or 0.0)
        if last > 0:
            return max(0.0, now - last)
        return 0.0

    def _preference_summary(self, speaker: str = "") -> str:
        spk = str(speaker or self.state.get("last_speaker") or "").strip()
        if not spk:
            return ""
        profile = self.relationship_memory.social_profile(spk)
        if not profile:
            return ""
        likes = profile.get("likes", []) if isinstance(profile.get("likes"), list) else []
        dislikes = profile.get("dislikes", []) if isinstance(profile.get("dislikes"), list) else []
        topics = profile.get("topics", []) if isinstance(profile.get("topics"), list) else []
        parts = []
        if likes:
            parts.append(f"likes={','.join(str(x) for x in likes[:3])}")
        if dislikes:
            parts.append(f"dislikes={','.join(str(x) for x in dislikes[:2])}")
        if topics:
            parts.append(f"topics={','.join(str(x) for x in topics[:3])}")
        trust = float(profile.get("trust_score", 0.0) or 0.0)
        parts.append(f"trust={trust:.2f}")
        return "; ".join(parts)

    def _recent_companion_activity_summary(self, limit: int = 4) -> str:
        db = self._social_db()
        if db is None:
            return ""
        try:
            rows = db.interaction_events.recent(limit=limit)
        except Exception:
            return ""
        bits = []
        for row in rows:
            kind = str(row.get("kind") or "").strip()
            if kind.startswith(("companion.", "appraisal:", "autonomy.")):
                bits.append(kind)
        return ", ".join(bits)

    def _habits_summary(self) -> str:
        """Summarize repeated habits, peak presence hours, and learned macro patterns."""
        import datetime
        from collections import Counter

        bits = []
        db = self._social_db()
        if db is not None:
            try:
                sightings = db.sightings.recent(limit=20)
                if len(sightings) >= 3:
                    hours = []
                    for s in sightings:
                        ts = float(s.get("ts", 0.0) or 0.0)
                        if ts > 0:
                            hours.append(datetime.datetime.fromtimestamp(ts).hour)
                    if hours:
                        top_hour, count = Counter(hours).most_common(1)[0]
                        bits.append(f"owner peak presence ~{top_hour:02d}:00")
            except Exception:
                pass

        shadow = getattr(self, "shadow_learner", None)
        if shadow is not None and hasattr(shadow, "get_learned_macros"):
            macros = shadow.get_learned_macros()
            if macros:
                m_names = list(macros.keys())[:3]
                bits.append(f"learned habits: {', '.join(m_names)}")

        return "; ".join(bits)

