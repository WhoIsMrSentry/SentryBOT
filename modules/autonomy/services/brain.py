import threading
import time
import logging
import random
import datetime
import json
from .client import ServiceClient
from .mood import MoodManager
from .memory import ShortTermMemory

logger = logging.getLogger("autonomy")

class AutonomyBrain:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None
        
        # Components
        self.mood = MoodManager(config)
        self.client = ServiceClient(config.get("endpoints", {}))
        self.memory = ShortTermMemory(max_items=20)
        
        # State
        self.state = {
            "last_interaction": time.time(),
            "is_bored": False,
            "is_sleeping": False,
            "last_speech_text": "",
            "last_speech_time": 0,
            "current_pan": 90,
            "current_tilt": 90
        }

    def start(self):
        if self.running:
            return
        self.running = True
        
        # Select default persona
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
            except Exception as e:
                logger.error(f"Error in autonomy loop: {e}")
            time.sleep(interval)

    def _sense(self):
        """Poll sensors for new information"""
        # 1. Check Speech Direction
        try:
            direction = self.client.get_speech_direction()
            if direction and "angle" in direction:
                angle = direction["angle"]
                if abs(angle) > 10: 
                    self._react_to_sound(angle)
        except Exception:
            pass

        # 2. Check Speech Text
        try:
            speech = self.client.get_last_speech()
            if speech and speech.get("final") and speech.get("text"):
                text = speech["text"]
                if text != self.state["last_speech_text"] and (time.time() - self.state["last_speech_time"] > 2):
                    self.state["last_speech_text"] = text
                    self.state["last_speech_time"] = time.time()
                    self._react_to_speech(text)
        except Exception:
            pass

    def _think(self):
        now = time.time()
        
        # 0. Check Circadian Rhythm
        self._check_sleep_cycle()
        
        if self.state["is_sleeping"]:
            if random.random() < 0.1:
                self.client.set_neopixel("breathe", emotions=["neutral"], duration=2.0)
            return

        # 1. Update Mood
        self.mood.update()
        
        # 2. Micro-movements (Breathing)
        if random.random() < 0.4:
            self._perform_micro_movement()

        # 3. Check Boredom & Agentic Decision
        boredom_threshold = self.config.get("defaults", {}).get("boredom_threshold_s", 20)
        time_since_interaction = now - self.state["last_interaction"]
        
        if time_since_interaction > boredom_threshold:
            if not self.state["is_bored"]:
                logger.info("Robot is bored.")
                self.state["is_bored"] = True
                self.mood.modify("curiosity", 10)
                self.memory.add_event("I became bored because nothing happened for a while.")
            
            # Agentic Decision making (instead of random)
            if random.random() < 0.2: # Don't spam LLM, check every few seconds
                self._make_agentic_decision()
        else:
            self.state["is_bored"] = False

    def _make_agentic_decision(self):
        """Ask LLM what to do based on internal state"""
        if not self.config.get("llm", {}).get("enabled", False):
            return

        # Construct prompt
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
            if resp:
                # Try to parse JSON from response (it might be wrapped in markdown)
                text = resp.get("answer", "")
                # Simple cleanup
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "{" in text:
                    text = text[text.find("{"):text.rfind("}")+1]
                
                decision = json.loads(text)
                action = decision.get("action")
                reason = decision.get("reason")
                
                logger.info(f"Agentic Decision: {action} because {reason}")
                self.memory.add_event(f"Decided to {action}: {reason}")
                
                self._execute_action(action)
                
        except Exception as e:
            logger.error(f"Agentic decision failed: {e}")

    def _execute_action(self, action):
        if action == "LOOK_AROUND":
            pan = random.randint(60, 120)
            tilt = random.randint(70, 110)
            self.state["current_pan"] = pan
            self.state["current_tilt"] = tilt
            self.client.move_head(pan, tilt)
        elif action == "BLINK":
            self.client.push_interaction_event("autonomy.blink")
        elif action == "SIGH":
            self.client.speak("Hıııh.")
            self.client.push_interaction_event("autonomy.bored")
        elif action == "STRETCH":
            self.client.move_head(45, 130)
            time.sleep(1)
            self.client.move_head(135, 130)
            time.sleep(1)
            self.client.move_head(90, 90)
        elif action == "MONOLOGUE":
            self._generate_monologue()

    def _react_to_sound(self, angle):
        """Turn head towards sound source"""
        logger.info(f"Sound detected at {angle}")
        self.client.push_interaction_event("autonomy.excited")
        self.state["last_interaction"] = time.time()
        self.mood.modify("curiosity", 5)
        self.mood.modify("energy", 2)
        self.memory.add_event(f"Heard sound at angle {angle}")

    def _react_to_speech(self, text):
        """React to heard text"""
        logger.info(f"Heard: {text}")
        self.state["last_interaction"] = time.time()
        self.mood.modify("happiness", 5)
        self.memory.add_event(f"User said: {text}")
        
        # Trigger excited interaction
        self.client.push_interaction_event("autonomy.excited")
        
        # Decide whether to use RAG (Knowledge) or Ollama (Chat/Persona)
        # Simple heuristic: If it sounds like a question about facts, use RAG.
        # Otherwise use Ollama.
        # In a real agent, we would ask the LLM to classify the intent.
        
        is_question = "?" in text or any(x in text.lower() for x in ["nedir", "kimdir", "nasıl", "what", "who", "how"])
        
        response_text = ""
        try:
            if is_question and self.config.get("wikirag", {}).get("enabled", False):
                logger.info("Routing to WikiRAG...")
                resp = self.client.chat_rag(text)
                if resp and "answer" in resp:
                    response_text = resp["answer"]
            else:
                logger.info("Routing to Ollama...")
                # We can inject current mood into the prompt context if we want
                # But Ollama module manages history. We just send the query.
                # Maybe prefix with mood?
                # For now, raw query.
                resp = self.client.chat(text)
                if resp and "answer" in resp:
                    response_text = resp["answer"]
            
            if response_text:
                logger.info(f"Reply: {response_text}")
                self.client.speak(response_text)
                self.memory.add_event(f"I replied: {response_text}")
                
        except Exception as e:
            logger.error(f"Failed to generate reply: {e}")

    def _perform_micro_movement(self):
        """Subtle servo movements to simulate breathing/alive-ness"""
        delta_tilt = random.randint(-2, 2)
        target_tilt = 90 + delta_tilt
        self.client.move_head(self.state["current_pan"], target_tilt)

    def _check_sleep_cycle(self):
        sleep_cfg = self.config.get("behaviors", {}).get("sleep", {})
        if not sleep_cfg.get("enabled", False):
            return

        hour = datetime.datetime.now().hour
        start = sleep_cfg.get("start_hour", 23)
        end = sleep_cfg.get("end_hour", 7)
        
        should_sleep = False
        if start > end:
            should_sleep = hour >= start or hour < end
        else:
            should_sleep = start <= hour < end
            
        if should_sleep and not self.state["is_sleeping"]:
            logger.info("Going to sleep...")
            self.state["is_sleeping"] = True
            self.memory.add_event("Going to sleep now.")
            self.client.push_interaction_event("autonomy.sleep")
            self.client.move_head(90, 120) # Head down
            self.client.speak("İyi geceler.")
            self.client.set_speech_tracking(False)
            
        elif not should_sleep and self.state["is_sleeping"]:
            logger.info("Waking up!")
            self.state["is_sleeping"] = False
            self.memory.add_event("Waking up from sleep.")
            self.mood.modify("energy", 100)
            self.client.push_interaction_event("autonomy.wake")
            self.client.speak("Günaydın.")
            self.client.set_speech_tracking(True)

    def _generate_monologue(self):
        if not self.config.get("llm", {}).get("enabled", False):
            return
            
        template = self.config.get("llm", {}).get("prompt_template", "")
        
        now = time.time()
        happiness = int(self.mood["happiness"])
        energy = int(self.mood["energy"])
        is_bored = "Evet" if self.state["is_bored"] else "Hayır"
        last_interaction_ago = int(now - self.state["last_interaction"])
        current_time = datetime.datetime.now().strftime("%H:%M")
        
        try:
            prompt = template.format(
                happiness=happiness,
                energy=energy,
                is_bored=is_bored,
                last_interaction_ago=last_interaction_ago,
                time=current_time
            )
            
            resp = self.client.chat(prompt)
            if resp and "answer" in resp:
                text = resp["answer"].strip('"')
                logger.info(f"Monologue: {text}")
                self.client.speak(text)
                self.memory.add_event(f"Said to myself: {text}")
        except Exception as e:
            logger.error(f"Monologue failed: {e}")
