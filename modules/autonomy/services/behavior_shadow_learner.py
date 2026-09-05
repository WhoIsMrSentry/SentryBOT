import logging
import time
import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.shadow_learner")

class BehaviorShadowLearner:
    """
    Shadow Mode / Behavior Cloning.
    Observes consecutive manual commands or API interactions.
    If a sequence is repeated multiple times, it is saved as a learned macro.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = bool(self.config.get("enabled", True))
        self.window_s = float(self.config.get("window_s", 15.0))
        self.min_repetitions = int(self.config.get("min_repetitions", 3))
        self.save_path = Path(str(self.config.get("save_path", "config/learned_behaviors.yml")))
        
        self.gap_s = float(self.config.get("gap_s", 5.0))
        
        self._current_episode: List[Dict[str, Any]] = []
        self._last_action_ts = 0.0
        self._learned_macros: Dict[str, Any] = self._load_macros()
        self._episode_counts: Dict[str, int] = {}
        
    def _load_macros(self) -> Dict[str, Any]:
        try:
            if self.save_path.exists():
                with open(self.save_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except Exception as exc:
            logger.error(f"Failed to load learned behaviors: {exc}")
        return {}

    def _save_macros(self):
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.save_path, "w", encoding="utf-8") as f:
                yaml.dump(self._learned_macros, f, allow_unicode=True)
        except Exception as exc:
            logger.error(f"Failed to save learned behaviors: {exc}")

    def observe_action(self, action_type: str, payload: Dict[str, Any]):
        """
        Record a manual user action (e.g., API command, remote control).
        """
        if not self.enabled:
            return
            
        now = time.time()
        
        # If there's a large gap, finalize the previous episode
        if self._current_episode and (now - self._last_action_ts) > self.gap_s:
            self._finalize_episode()
            
        self._current_episode.append({
            "type": action_type,
            "payload": payload
        })
        self._last_action_ts = now

    def _finalize_episode(self):
        if len(self._current_episode) < 2:
            self._current_episode.clear()
            return
            
        sequence = " -> ".join([a["type"] for a in self._current_episode])
        
        if sequence not in self._episode_counts:
            self._episode_counts[sequence] = 0
            
        self._episode_counts[sequence] += 1
        
        if self._episode_counts[sequence] >= self.min_repetitions:
            macro_name = f"learned_macro_{hash(sequence) % 10000}"
            if macro_name not in self._learned_macros:
                logger.info(f"SHADOW MODE: Learned a new behavior macro: {sequence}")
                self._learned_macros[macro_name] = {
                    "sequence": sequence,
                    "actions": list(self._current_episode)
                }
                self._save_macros()
                
        self._current_episode.clear()

    def get_learned_macros(self) -> Dict[str, Any]:
        """Return dict of all learned macros."""
        return dict(self._learned_macros)

    def replay_macro(self, macro_name: str, client: Any) -> bool:
        """Replay the actions belonging to a learned macro."""
        macro = self._learned_macros.get(macro_name)
        if not macro or not client:
            return False

        actions = macro.get("actions", [])
        logger.info(f"SHADOW MODE: Replaying macro {macro_name} with {len(actions)} actions")
        for action in actions:
            act_type = action.get("type")
            payload = action.get("payload", {})
            try:
                if act_type == "head_move" and hasattr(client, "move_head"):
                    client.move_head(payload.get("pan", 90), payload.get("tilt", 90))
                elif act_type == "neopixel" and hasattr(client, "set_neopixel"):
                    client.set_neopixel(
                        mode=payload.get("mode", "solid"),
                        emotions=payload.get("emotions", ["neutral"]),
                    )
                elif act_type == "express_emotion" and hasattr(client, "express_emotion"):
                    client.express_emotion(
                        emotion=payload.get("emotion", "neutral"),
                        intensity=payload.get("intensity", 0.8),
                    )
                elif act_type == "speak" and hasattr(client, "speak"):
                    client.speak(payload.get("text", ""))
                elif hasattr(client, "queue_action"):
                    client.queue_action(act_type, priority=60, payload=payload)
            except Exception as exc:
                logger.warning(f"Failed replaying macro action {act_type}: {exc}")
        return True

