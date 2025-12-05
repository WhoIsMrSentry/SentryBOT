import threading
import time
import logging
import random
import datetime
import json

from .client import ServiceClient
from .mood import MoodManager
from .memory import ShortTermMemory
from .brain_parts.animations import AnimationSupportMixin
from .brain_parts.owner_guard import OwnerGuardMixin
from .brain_parts.timeline import TimelineMixin
from .brain_parts.vision import VisionMixin
from .brain_parts.vocal import VocalMixin

logger = logging.getLogger("autonomy")


class AutonomyBrain(
    AnimationSupportMixin,
    TimelineMixin,
    OwnerGuardMixin,
    VisionMixin,
    VocalMixin,
):
    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None

        # Components
        self.mood = MoodManager(config)
        self.client = ServiceClient(config.get("endpoints", {}))
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
        }
        self._people_last_seen = {}
        self._last_emotion_sent = None
        self._current_people = {}
        self._attempt_log = []
        self._owner_report_pending = False
        self._last_owner_scan = 0.0
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
            if direction and "angle" in direction:
                angle = direction["angle"]
                if abs(angle) > 10:
                    self._react_to_sound(angle)
        except Exception:
            pass

    def _sense_speech_text(self):
        try:
            speech = self.client.get_last_speech()
            if speech and speech.get("final") and speech.get("text"):
                text = speech["text"]
                elapsed = time.time() - self.state["last_speech_time"]
                if text != self.state["last_speech_text"] and elapsed > 2:
                    self.state["last_speech_text"] = text
                    self.state["last_speech_time"] = time.time()
                    self._react_to_speech(text)
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
            if random.random() < 0.2:
                self._make_agentic_decision()
        else:
            self.state["is_bored"] = False

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
            if not self._trigger_animation("look_around"):
                self._head_scan_fallback()
        elif action == "BLINK":
            if not self._trigger_animation("blink"):
                self._blink_fallback()
        elif action == "SIGH":
            self._speak_with_mood("Hıııh.", emotion="tired")
            self.client.push_interaction_event("autonomy.bored")
        elif action == "STRETCH":
            if not self._trigger_animation("stretch"):
                self._stretch_fallback()
        elif action == "MONOLOGUE":
            self._generate_monologue()

    def _react_to_sound(self, angle):
        """Turn head towards sound source."""
        logger.info("Sound detected at %s", angle)
        offset = max(-70, min(70, angle))
        target_pan = max(0, min(180, 90 + offset))
        self.state["current_pan"] = target_pan
        self.client.move_head(target_pan, self.state["current_tilt"])
        self.client.push_interaction_event("autonomy.excited")
        self.state["last_interaction"] = time.time()
        self.mood.modify("curiosity", 5)
        self.mood.modify("energy", 2)
        self.memory.add_event(f"Heard sound at angle {angle}")

    def _react_to_speech(self, text):
        """React to heard text."""
        logger.info("Heard: %s", text)
        self.state["last_interaction"] = time.time()
        self.mood.modify("happiness", 5)
        self.memory.add_event(f"User said: {text}")
        self._log_conversation(text)
        speaker = self._guess_active_person()
        if speaker:
            self.state["last_speaker"] = speaker

        self.client.push_interaction_event("autonomy.excited")

        blocked_response = self._maybe_block_request(text)
        if blocked_response:
            message, emotion = blocked_response
            self._speak_with_mood(message, emotion=emotion)
            return

        if self._handle_owner_commands(text, speaker):
            return

        if self._features_locked_for_request(text):
            return

        is_question = "?" in text or any(
            key in text.lower() for key in ["nedir", "kimdir", "nasıl", "what", "who", "how"]
        )

        response_text = ""
        try:
            if is_question and self.config.get("wikirag", {}).get("enabled", False):
                logger.info("Routing to WikiRAG...")
                resp = self.client.chat_rag(text)
                if resp and "answer" in resp:
                    response_text = resp["answer"]
            else:
                logger.info("Routing to Ollama...")
                resp = self.client.chat(text)
                if resp and "answer" in resp:
                    response_text = resp["answer"]

            if response_text:
                logger.info("Reply: %s", response_text)
                self._speak_with_mood(response_text)
                self.memory.add_event(f"I replied: {response_text}")
        except Exception as exc:
            logger.error("Failed to generate reply: %s", exc)

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
            self.client.move_head(90, 120)
            self._speak_with_mood("İyi geceler.", emotion="tired")
            self.client.set_speech_tracking(False)

        elif not should_sleep and self.state["is_sleeping"]:
            logger.info("Waking up!")
            self.state["is_sleeping"] = False
            self.memory.add_event("Waking up from sleep.")
            self.mood.modify("energy", 100)
            self.client.push_interaction_event("autonomy.wake")
            self._speak_with_mood("Günaydın.", emotion="joy")
            self.client.set_speech_tracking(True)
