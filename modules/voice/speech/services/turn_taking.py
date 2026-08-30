"""Dynamic Turn-Taking Engine (Dinamik Sıra Takibi ve Konuşma Sırası Algısı).

Kör ve mekanik 8 saniyelik bekleme sayaçları yerine, kullanıcının konuşmasını
tamamlayıp tamamlamadığını VAD (Ses Aktivite Tespiti), sessizlik süresi ve
akustik tonlama ile sezer.

Konuşma Sırası Durumları (Turn States):
- IDLE: Boşta, ortam dinleniyor.
- USER_SPEAKING: Kullanıcı aktif konuşuyor.
- USER_PAUSED: Kullanıcı konuşurken duraksadı (örneğin kelime arıyor - henüz bitirmedi).
- USER_DONE: Kullanıcı sözünü bitirdi; sıra robota geçti.
- PROMPT_CUE: Kullanıcı duraksadı ve sessizlik uzadı (robot hafifçe başını eğer veya "Dinliyorum?" der).
"""

from __future__ import annotations
import time
from enum import Enum
from typing import Any, Dict, Optional

class TurnState(str, Enum):
    IDLE = "idle"
    USER_SPEAKING = "user_speaking"
    USER_PAUSED = "user_paused"
    USER_DONE = "user_done"
    PROMPT_CUE = "prompt_cue"

class DynamicTurnTakingEngine:
    def __init__(
        self,
        min_speech_duration_s: float = 0.4,
        end_of_turn_silence_s: float = 0.85,
        hesitation_pause_s: float = 2.2,
        max_turn_timeout_s: float = 12.0,
    ) -> None:
        self.min_speech_duration_s = min_speech_duration_s
        self.end_of_turn_silence_s = end_of_turn_silence_s
        self.hesitation_pause_s = hesitation_pause_s
        self.max_turn_timeout_s = max_turn_timeout_s

        self.state = TurnState.IDLE
        self._turn_start_ts = 0.0
        self._last_speech_ts = 0.0
        self._cue_emitted = False

    def start_listening(self, current_time_s: Optional[float] = None) -> None:
        now = float(current_time_s if current_time_s is not None else time.time())
        self.state = TurnState.IDLE
        self._turn_start_ts = now
        self._last_speech_ts = 0.0
        self._cue_emitted = False

    def process_vad_frame(self, is_speech: bool, current_time_s: Optional[float] = None) -> Dict[str, Any]:
        now = float(current_time_s if current_time_s is not None else time.time())
        
        # 1. Konuşma başladı
        if is_speech:
            if self._last_speech_ts == 0.0:
                self._turn_start_ts = now
            self._last_speech_ts = now
            self.state = TurnState.USER_SPEAKING
            return {"state": self.state.value, "turn_completed": False, "suggested_cue": None}

        # 2. Henüz hiç konuşma duyulmadıysa
        if self._last_speech_ts == 0.0:
            if now - self._turn_start_ts > self.max_turn_timeout_s:
                self.state = TurnState.USER_DONE
                return {"state": self.state.value, "turn_completed": True, "timeout": True, "suggested_cue": None}
            return {"state": self.state.value, "turn_completed": False, "suggested_cue": None}

        # 3. Konuşuldu ve şu an sessizlik var
        silence_duration = now - self._last_speech_ts
        speech_duration = self._last_speech_ts - self._turn_start_ts

        # Kullanıcı yeterli süre konuştu ve ardından doğal konuşma sonu sessizliği oluştu
        if speech_duration >= self.min_speech_duration_s and silence_duration >= self.end_of_turn_silence_s:
            self.state = TurnState.USER_DONE
            return {"state": self.state.value, "turn_completed": True, "suggested_cue": None}

        # Sessizlik biraz uzadıysa ama henüz timeout olmadıysa (kullanıcı düşünüyor olabilir)
        if silence_duration >= self.hesitation_pause_s and not self._cue_emitted:
            self._cue_emitted = True
            self.state = TurnState.PROMPT_CUE
            return {
                "state": self.state.value,
                "turn_completed": False,
                "suggested_cue": "head_tilt_listening",
            }

        self.state = TurnState.USER_PAUSED
        return {"state": self.state.value, "turn_completed": False, "suggested_cue": None}
