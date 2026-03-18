import threading
import time
import logging
import random
import datetime
import json
from typing import List

from .client import ServiceClient
from .idle_behaviors import IdleBehaviorPlanner
from .mood import MoodManager
from .memory import ShortTermMemory
from .brain_parts.animations import AnimationSupportMixin
from .brain_parts.owner_guard import OwnerGuardMixin
from .brain_parts.responses import ResponseTagMixin
from .brain_parts.scenes import SceneMixin
from .brain_parts.timeline import TimelineMixin
from .brain_parts.vision import VisionMixin
from .brain_parts.vocal import VocalMixin

logger = logging.getLogger("autonomy")


class AutonomyBrain(
    AnimationSupportMixin,
    TimelineMixin,
    OwnerGuardMixin,
    ResponseTagMixin,
    SceneMixin,
    VisionMixin,
    VocalMixin,
):
    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None

        # Components
        self.mood = MoodManager(config)
        self.client = ServiceClient(config.get("endpoints", {}), config=config)
        self.idle_planner = IdleBehaviorPlanner(config)
        self.memory = ShortTermMemory(max_items=20)
        self._vision_cfg = config.get("vision_hooks", {})
        self.owner_cfg = config.get("owner", {})

        # State
        self.state = {
            "last_interaction": time.time(),
            "is_bored": False,
            "is_sleeping": False,
            "last_speech_text": "",
            "last_speech_time": 0,
            "last_speech_language": "tr",
            "current_pan": 90,
            "current_tilt": 90,
            "last_emotion": None,
            "last_vision_poll": 0.0,
            "owner_last_seen": 0.0,
            "owner_lockout_until": 0.0,
            "owner_last_greet": 0.0,
            "owner_permission_until": 0.0,
            "temp_owner": None,
            "temp_owner_expires": 0.0,
            "rfid_authorized_until": 0.0,
            "last_speaker": None,
            "persona_mode": None,
        }
        self._people_last_seen = {}
        self._last_emotion_sent = None
        self._current_people = {}
        self._attempt_log = []
        self._owner_report_pending = False
        self._last_owner_scan = 0.0
        self._last_idle_action = 0.0
        self._reset_daily_timeline()

    def start(self):
        if self.running:
            return
        self.running = True

        try:
            self.client.select_persona("sentry")
        except Exception:
            logger.warning("Failed to select persona 'sentry'")

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("Autonomy Brain started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Autonomy Brain stopped.")

    def _loop(self):
        interval = self.config.get("defaults", {}).get("loop_interval_ms", 1000) / 1000.0
        while self.running:
            try:
                self._sense()
                self._think()
            except Exception as exc:
                logger.error("Error in autonomy loop: %s", exc)
            time.sleep(interval)

    def interaction_occurred(self, source=None):
        """External ping that resets boredom timer and nudges mood."""
        self.state["last_interaction"] = time.time()
        self.state["is_bored"] = False
        if source:
            self.state["last_speaker"] = source
        self.mood.modify("happiness", 1)

    def _sense(self):
        """Poll sensors for new information."""
        self._sense_sound_direction()
        self._sense_speech_text()
        self._sense_vision()

    def _sense_sound_direction(self):
        try:
            direction = self.client.get_speech_direction()
            angle = (direction or {}).get("angle") if isinstance(direction, dict) else None
            if isinstance(angle, (int, float)) and abs(angle) > 10:
                    self._react_to_sound(angle)
        except Exception:
            pass

    def _sense_speech_text(self):
        try:
            speech = self.client.get_last_speech()
            if speech and speech.get("final") and speech.get("text"):
                text = speech["text"]
                lang = str(speech.get("language") or self.state.get("last_speech_language") or "tr")
                elapsed = time.time() - self.state["last_speech_time"]
                if text != self.state["last_speech_text"] and elapsed > 2:
                    self.state["last_speech_text"] = text
                    self.state["last_speech_time"] = time.time()
                    self.state["last_speech_language"] = lang
                    self._react_to_speech(text, source_lang=lang)
        except Exception:
            pass

    def _sync_emotion(self):
        dominant = self.mood.get_dominant_emotion()
        if not dominant or dominant == self._last_emotion_sent:
            return
        self._last_emotion_sent = dominant
        self.state["last_emotion"] = dominant
        self.client.update_emotions([dominant])
        self.client.push_interaction_event(f"emotion.{dominant}")

    def _think(self):
        now = time.time()
        self._ensure_timeline_day()
        self._refresh_rfid_authorization()

        self._check_sleep_cycle()
        if self.state["is_sleeping"]:
            if random.random() < 0.1:
                self.client.set_neopixel("breathe", emotions=["neutral"], duration=2.0)
            return

        self.mood.update()
        self._sync_emotion()

        if random.random() < 0.4:
            self._perform_micro_movement()

        self._maybe_scan_for_owner()

        boredom_threshold = self.config.get("defaults", {}).get("boredom_threshold_s", 20)
        time_since_interaction = now - self.state["last_interaction"]
        if time_since_interaction > boredom_threshold:
            if not self.state["is_bored"]:
                logger.info("Robot is bored.")
                self.state["is_bored"] = True
                self.mood.modify("curiosity", 10)
                self.memory.add_event("I became bored because nothing happened for a while.")
            idle_cfg = self.config.get("behaviors", {}).get("idle_tree", {})
            idle_interval = float(idle_cfg.get("interval_s", 6.0))
            if now - self._last_idle_action >= idle_interval:
                if self._run_idle_behavior(now):
                    self._last_idle_action = now
                elif bool(idle_cfg.get("fallback_to_llm", True)) and random.random() < 0.2:
                    self._make_agentic_decision()
        else:
            self.state["is_bored"] = False

    def _run_idle_behavior(self, now: float) -> bool:
        choice = self.idle_planner.pick(now=now)
        if choice is None:
            return False
        logger.info("Idle behavior selected: %s", choice.name)
        self.idle_planner.stamp(choice.name, now=now)
        self.memory.add_event(f"Idle action: {choice.name}")
        self._execute_action(choice.name)
        return True

    def _make_agentic_decision(self):
        """Ask LLM what to do based on internal state."""
        if not self.config.get("llm", {}).get("enabled", False):
            return

        events = "\n".join(self.memory.get_recent_events())
        prompt = f"""
        You are SentryBOT. You are currently bored.

        Internal State:
        - Happiness: {int(self.mood['happiness'])}/100
        - Energy: {int(self.mood['energy'])}/100
        - Curiosity: {int(self.mood['curiosity'])}/100

        Recent Events:
        {events}

        Available Actions:
        - LOOK_AROUND: Move head to look at surroundings.
        - SIGH: Make a sigh sound and dim lights.
        - STRETCH: Move head up and down to stretch.
        - MONOLOGUE: Say something short to yourself about your state.
        - BLINK: Blink eyes (lights).

        DECISION FORMAT: JSON with keys "action" (one of above) and "reason" (short string).
        Example: {{"action": "LOOK_AROUND", "reason": "I want to see if anyone is there."}}

        Make a decision now.
        """

        try:
            resp = self.client.chat(prompt)
            if not resp:
                return
            text = resp.get("answer", "")
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "{" in text:
                text = text[text.find("{"):text.rfind("}") + 1]

            decision = json.loads(text)
            action = decision.get("action")
            reason = decision.get("reason")

            logger.info("Agentic Decision: %s because %s", action, reason)
            self.memory.add_event(f"Decided to {action}: {reason}")
            self._execute_action(action)
        except Exception as exc:
            logger.error("Agentic decision failed: %s", exc)

    def _execute_action(self, action):
        if action == "LOOK_AROUND":
            self.client.push_interaction_event("autonomy.look_around")
            if not self._trigger_animation("look_around"):
                self._head_scan_fallback()
        elif action == "BLINK":
            # Always emit a visual event so LED/OLED can react even if
            # servo animation endpoint reports success while degrading.
            self.client.push_interaction_event("autonomy.blink")
            if not self._trigger_animation("blink"):
                self._blink_fallback()
        elif action == "SIGH":
            self._speak_with_mood("Hıııh.", emotion="tired")
            self.client.push_interaction_event("autonomy.bored")
        elif action == "STRETCH":
            self.client.push_interaction_event("autonomy.stretch")
            if not self._trigger_animation("stretch"):
                self._stretch_fallback()
        elif action == "MONOLOGUE":
            self.client.push_interaction_event("autonomy.monologue")
            self._generate_monologue()

    def _react_to_sound(self, angle):
        """Turn head towards sound source."""
        logger.info("Sound detected at %s", angle)
        offset = max(-70, min(70, angle))
        target_pan = max(0, min(180, 90 + offset))
        self.state["current_pan"] = target_pan
        ran = self._run_scene(
            "curious_scan",
            context={"angle": int(angle), "target_pan": int(target_pan)},
        )
        if not ran:
            self.client.move_head(target_pan, self.state["current_tilt"])
        self.client.push_interaction_event("autonomy.excited")
        self.state["last_interaction"] = time.time()
        self.mood.modify("curiosity", 5)
        self.mood.modify("energy", 2)
        self.memory.add_event(f"Heard sound at angle {angle}")

    def _react_to_speech(self, text, source_lang: str | None = None):
        """React to heard text."""
        logger.info("Heard: %s", text)
        self.state["last_interaction"] = time.time()
        self.mood.modify("happiness", 5)
        self.memory.add_event(f"User said: {text}")
        self._log_conversation(text)
        lang = str(source_lang or self.state.get("last_speech_language") or "tr")
        low = str(text or "").lower()
        if any(k in low for k in ["hey sentry", "hey sentrybot", "sentry", "sentrybot"]):
            self._run_scene("wakeword_reaction", context={"text": text})
        speaker = self._guess_active_person()
        if speaker:
            self.state["last_speaker"] = speaker

        self.client.push_interaction_event("autonomy.excited")

        blocked_response = self._maybe_block_request(text)
        if blocked_response:
            message, emotion = blocked_response
            self._speak_with_mood(message, emotion=emotion, language=lang)
            return

        if self._handle_owner_commands(text, speaker):
            return

        if self._features_locked_for_request(text):
            return

        is_question = "?" in text or any(
            key in text.lower() for key in ["nedir", "kimdir", "nasıl", "what", "who", "how"]
        )

        offline_cfg = self.config.get("offline_mode", {})
        if bool(offline_cfg.get("enabled", False)):
            target_service = "wiki_rag" if is_question and self.config.get("wikirag", {}).get("enabled", False) else "ollama"
            if not self.client.is_service_available(target_service):
                fallback = self._offline_reply(text, target_service)
                self.client.push_interaction_event("autonomy.offline", {"service": target_service})
                self._speak_with_mood(fallback, emotion="neutral", language=lang)
                self.memory.add_event(f"Offline fallback reply used for {target_service}: {fallback}")
                return

        response_text = ""
        response_actions = None
        raw_response = None
        try:
            if is_question and self.config.get("wikirag", {}).get("enabled", False):
                logger.info("Routing to WikiRAG...")
                rag_query = text
                tr = self.client.translate(text, source_lang="auto", target_lang="en")
                detected_lang = lang
                if isinstance(tr, dict) and tr.get("ok"):
                    if tr.get("text"):
                        rag_query = str(tr.get("text"))
                    if tr.get("source_lang"):
                        detected_lang = str(tr.get("source_lang"))
                resp = self.client.chat_rag(rag_query)
                if resp and "answer" in resp:
                    response_text = resp["answer"]
                    response_actions = resp.get("actions")
                    raw_response = resp.get("raw")
                    if detected_lang.lower() != "en" and response_text:
                        tr_back = self.client.translate(response_text, source_lang="en", target_lang=detected_lang)
                        if isinstance(tr_back, dict) and tr_back.get("ok") and tr_back.get("text"):
                            response_text = str(tr_back.get("text"))
                            lang = detected_lang
            else:
                logger.info("Routing to Ollama...")
                resp = self.client.chat(text, source_lang="auto", response_lang=None)
                if resp and "answer" in resp:
                    response_text = resp["answer"]
                    response_actions = resp.get("actions")
                    raw_response = resp.get("raw")
                    trans = resp.get("translation") if isinstance(resp, dict) else None
                    if isinstance(trans, dict) and trans.get("response_lang"):
                        lang = str(trans.get("response_lang"))

            if response_text:
                clean_text = self.apply_llm_response(response_text, response_actions, raw_response, speak=False)
                if clean_text:
                    self._speak_with_mood(clean_text, language=lang)
                    logger.info("Reply: %s", clean_text)
                    self.memory.add_event(f"I replied: {clean_text}")
                else:
                    logger.info("LLM response only triggered physical actions.")
        except Exception as exc:
            logger.error("Failed to generate reply: %s", exc)

    def _offline_reply(self, text: str, service: str) -> str:
        cfg = self.config.get("offline_mode", {})
        context = self._offline_context_label(text)
        contextual = cfg.get("contextual_replies", {}) if isinstance(cfg.get("contextual_replies", {}), dict) else {}
        ctx_pool = contextual.get(context)
        if isinstance(ctx_pool, list) and ctx_pool:
            return str(random.choice(ctx_pool))
        persona = cfg.get("persona_replies", {}) if isinstance(cfg.get("persona_replies", {}), dict) else {}
        mood_key = str(self.mood.get_dominant_emotion() or "neutral")
        mood_replies = persona.get(mood_key)
        if isinstance(mood_replies, list) and mood_replies:
            return str(random.choice(mood_replies))
        neutral_replies = persona.get("neutral")
        if isinstance(neutral_replies, list) and neutral_replies:
            return str(random.choice(neutral_replies))
        replies: List[str] = cfg.get("fallback_replies", []) if isinstance(cfg.get("fallback_replies", []), list) else []
        if replies:
            return str(random.choice(replies))
        if "?" in str(text):
            return "Su an baglanti yok, ama birazdan tekrar deneyebilirim."
        return f"Su an {service} ulasilamiyor, yine de buradayim."

    @staticmethod
    def _offline_context_label(text: str) -> str:
        t = str(text or "").strip().lower()
        if not t:
            return "generic"
        if "?" in t:
            return "question"
        if any(k in t for k in ["merhaba", "selam", "hey", "gunaydin", "iyi aksamlar"]):
            return "greeting"
        if any(k in t for k in ["yap", "ac", "kapat", "calistir", "dur", "git", "don"]):
            return "command"
        return "generic"

    def apply_llm_response(
        self,
        text: str,
        actions: dict | None = None,
        raw_text: str | None = None,
        speak: bool = False,
    ) -> str:
        """Harici modüllerin persona etiketlerini işletmesine izin ver."""
        clean = self._handle_llm_actions(text or "", actions, raw_text)
        if speak and clean:
            self._speak_with_mood(clean)
        return clean

    def update_palettes(self, palettes: dict[str, list[int]]) -> None:
        """Refresh in-memory palette cache after config edits."""
        defaults = self.config.setdefault("defaults", {})
        lights = defaults.setdefault("lights", {})
        lights["palettes"] = dict(palettes)

    def _check_sleep_cycle(self):
        sleep_cfg = self.config.get("behaviors", {}).get("sleep", {})
        if not sleep_cfg.get("enabled", False):
            return

        hour = datetime.datetime.now().hour
        start = sleep_cfg.get("start_hour", 23)
        end = sleep_cfg.get("end_hour", 7)

        if start > end:
            should_sleep = hour >= start or hour < end
        else:
            should_sleep = start <= hour < end

        if should_sleep and not self.state["is_sleeping"]:
            logger.info("Going to sleep...")
            self._deliver_timeline_summary()
            self.state["is_sleeping"] = True
            self.memory.add_event("Going to sleep now.")
            self.client.push_interaction_event("autonomy.sleep")
            ran = self._run_scene("sleepy_entry", context={"hour": hour})
            if not ran:
                self.client.move_head(90, 120)
                self._speak_with_mood("İyi geceler.", emotion="tired")
            self.client.set_speech_tracking(False)

        elif not should_sleep and self.state["is_sleeping"]:
            logger.info("Waking up!")
            self.state["is_sleeping"] = False
            self.memory.add_event("Waking up from sleep.")
            self.mood.modify("energy", 100)
            self.client.push_interaction_event("autonomy.wake")
            if not self._run_scene("wake_entry", context={"hour": hour}):
                self._speak_with_mood("Günaydın.", emotion="joy")
            self.client.set_speech_tracking(True)
