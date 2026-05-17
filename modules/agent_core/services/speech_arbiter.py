"""Speech arbitration for SentryBOT.

Ensures only one TTS utterance plays at a time, manages a priority queue,
cancels stale progress messages when final response arrives, and sets an
echo-guard flag so Vosk can pause during TTS playback.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agent.speech_arbiter")


# ── Priority tiers ────────────────────────────────────────────────────
class SpeechPriority:
    SAFETY = 95
    FINAL_RESPONSE = 60
    PROGRESS = 30
    IDLE = 15


@dataclass
class SpeechItem:
    """A single TTS utterance submitted to the arbiter."""

    text: str
    priority: int = SpeechPriority.PROGRESS
    category: str = "progress"  # progress | final | safety | idle
    cancel_token: str = ""
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    created_at: float = field(default_factory=time.time)
    max_age_s: float = 10.0  # auto-expire if queued too long
    language: str = ""
    tone: Optional[Dict[str, Any]] = None

    @property
    def expired(self) -> bool:
        return time.time() - self.created_at > self.max_age_s


class SpeechArbiter:
    """Thread-safe TTS arbitration layer.

    Usage::

        arbiter = SpeechArbiter(speak_fn=my_tts_function)
        arbiter.start()

        # Submit speech items
        arbiter.enqueue("Bakıyorum...", priority=SpeechPriority.PROGRESS,
                        category="progress", cancel_token="req_123")

        # When final answer arrives, cancel stale progress and speak final
        arbiter.cancel_by_token("req_123")
        arbiter.enqueue("İşte sonuç...", priority=SpeechPriority.FINAL_RESPONSE,
                        category="final")
    """

    def __init__(
        self,
        speak_fn: Optional[Callable[..., Any]] = None,
        max_queue_size: int = 10,
    ) -> None:
        self._speak_fn = speak_fn
        self._max_queue = max(3, int(max_queue_size))

        self._lock = threading.Lock()
        self._queue: List[SpeechItem] = []
        self._processing = threading.Event()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        # Echo guard: set True while TTS is playing so Vosk can pause
        self.tts_active = threading.Event()

        # Dedup: last spoken text hash within window
        self._recent_texts: Dict[str, float] = {}
        self._dedup_window_s = 5.0

        # Currently speaking item (for external query)
        self._current_item: Optional[SpeechItem] = None
        self._tts_state_callback: Optional[Callable[[bool], Any]] = None
        self._stop_playback_fn: Optional[Callable[[], Any]] = None
        self._interrupt_flag = threading.Event()

    # ── Lifecycle ─────────────────────────────────────────────────────
    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, daemon=True, name="speech_arbiter")
        self._worker.start()
        logger.info("SpeechArbiter started.")

    def stop(self) -> None:
        self._stop_event.set()
        self._processing.set()  # wake up worker
        if self._worker:
            self._worker.join(timeout=2.0)
        logger.info("SpeechArbiter stopped.")

    def set_speak_fn(self, fn: Callable[..., Any]) -> None:
        self._speak_fn = fn

    def set_tts_state_callback(self, fn: Callable[[bool], Any]) -> None:
        self._tts_state_callback = fn

    def set_stop_playback_fn(self, fn: Callable[[], Any]) -> None:
        self._stop_playback_fn = fn

    def interrupt_all(self) -> int:
        """Cancel queued TTS and stop current speaker output (wakeword barge-in)."""
        self._interrupt_flag.set()
        cleared = self.clear_queue()
        self.cancel_progress()
        if self._stop_playback_fn is not None:
            try:
                self._stop_playback_fn()
            except Exception as exc:
                logger.debug("stop_playback_fn failed: %s", exc)
        with self._lock:
            self._current_item = None
        self.tts_active.clear()
        if self._tts_state_callback is not None:
            try:
                self._tts_state_callback(False)
            except Exception:
                pass
        logger.info("SpeechArbiter interrupted (cleared=%d)", cleared)
        return cleared

    # ── Submit ────────────────────────────────────────────────────────
    def enqueue(
        self,
        text: str,
        priority: int = SpeechPriority.PROGRESS,
        category: str = "progress",
        cancel_token: str = "",
        language: str = "",
        tone: Optional[Dict[str, Any]] = None,
        max_age_s: float = 10.0,
    ) -> Optional[str]:
        """Add a speech item to the queue. Returns item_id or None if rejected."""
        text = str(text or "").strip()
        if not text:
            return None

        # Dedup check
        now = time.time()
        text_key = text[:80].lower()
        with self._lock:
            last = self._recent_texts.get(text_key, 0.0)
            if now - last < self._dedup_window_s:
                return None

        item = SpeechItem(
            text=text,
            priority=priority,
            category=category,
            cancel_token=cancel_token,
            language=language,
            tone=tone,
            max_age_s=max_age_s,
        )

        with self._lock:
            # Drop expired items
            self._queue = [i for i in self._queue if not i.expired]

            # Enforce max queue size – drop lowest priority
            if len(self._queue) >= self._max_queue:
                self._queue.sort(key=lambda x: x.priority)
                if item.priority <= self._queue[0].priority:
                    return None  # reject
                self._queue.pop(0)  # drop lowest

            self._queue.append(item)
            self._queue.sort(key=lambda x: -x.priority)  # highest first

        self._processing.set()  # wake worker
        return item.item_id

    def enqueue_progress(
        self,
        text: str,
        cancel_token: str = "",
        language: str = "",
    ) -> Optional[str]:
        """Convenience: enqueue a progress-level message."""
        return self.enqueue(
            text=text,
            priority=SpeechPriority.PROGRESS,
            category="progress",
            cancel_token=cancel_token,
            language=language,
            max_age_s=8.0,
        )

    def enqueue_final(self, text: str, language: str = "", tone: Optional[Dict] = None) -> Optional[str]:
        """Convenience: enqueue a final-response-level message."""
        # Final answer should preempt stale progress chatter.
        self.cancel_progress()
        text = str(text or "").strip()
        if not text:
            return None

        # Micro-staging for long final answers: speak first clause ASAP, then remainder.
        first_chunk = text
        remainder = ""
        if len(text) > 140:
            cut = max(text.find(". "), text.find("? "), text.find("! "))
            if 40 < cut < 220:
                first_chunk = text[: cut + 1].strip()
                remainder = text[cut + 1 :].strip()

        first_id = self.enqueue(
            text=first_chunk,
            priority=SpeechPriority.FINAL_RESPONSE,
            category="final",
            language=language,
            tone=tone,
            max_age_s=30.0,
        )
        if remainder:
            self.enqueue(
                text=remainder,
                priority=SpeechPriority.FINAL_RESPONSE - 1,
                category="final",
                language=language,
                tone=tone,
                max_age_s=30.0,
            )
        return first_id

    def enqueue_safety(self, text: str) -> Optional[str]:
        """Convenience: enqueue a safety-level message (highest priority)."""
        return self.enqueue(
            text=text,
            priority=SpeechPriority.SAFETY,
            category="safety",
            max_age_s=15.0,
        )

    # ── Cancel ────────────────────────────────────────────────────────
    def cancel_by_token(self, cancel_token: str) -> int:
        """Cancel all queued items with the given cancel_token."""
        if not cancel_token:
            return 0
        count = 0
        with self._lock:
            before = len(self._queue)
            self._queue = [i for i in self._queue if i.cancel_token != cancel_token]
            count = before - len(self._queue)
        if count:
            logger.debug("Cancelled %d speech items with token '%s'", count, cancel_token)
        return count

    def cancel_progress(self) -> int:
        """Cancel all queued progress messages."""
        count = 0
        with self._lock:
            before = len(self._queue)
            self._queue = [i for i in self._queue if i.category != "progress"]
            count = before - len(self._queue)
        return count

    def clear_queue(self) -> int:
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    # ── Query ─────────────────────────────────────────────────────────
    def is_speaking(self) -> bool:
        return self.tts_active.is_set()

    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "speaking": self.tts_active.is_set(),
                "queue_size": len(self._queue),
                "current": self._current_item.text[:60] if self._current_item else None,
            }

    # ── Worker ────────────────────────────────────────────────────────
    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._processing.wait(timeout=1.0)
            self._processing.clear()

            while not self._stop_event.is_set():
                item = self._pop_next()
                if item is None:
                    break
                self._dispatch(item)

    def _pop_next(self) -> Optional[SpeechItem]:
        with self._lock:
            # Remove expired
            self._queue = [i for i in self._queue if not i.expired]
            if not self._queue:
                return None
            # Already sorted by priority (highest first)
            return self._queue.pop(0)

    def _dispatch(self, item: SpeechItem) -> None:
        if self._interrupt_flag.is_set():
            self._interrupt_flag.clear()
            return
        if not self._speak_fn:
            logger.debug("No speak_fn set, dropping: %s", item.text[:40])
            return

        # Record for dedup
        text_key = item.text[:80].lower()
        with self._lock:
            self._recent_texts[text_key] = time.time()
            self._current_item = item
            # GC old dedup entries
            if len(self._recent_texts) > 50:
                cutoff = time.time() - self._dedup_window_s * 2
                self._recent_texts = {
                    k: v for k, v in self._recent_texts.items() if v > cutoff
                }

        self.tts_active.set()
        if self._tts_state_callback is not None:
            try:
                self._tts_state_callback(True)
            except Exception:
                pass
        try:
            if self._interrupt_flag.is_set():
                return
            kwargs: Dict[str, Any] = {"text": item.text}
            if item.tone:
                kwargs["tone"] = item.tone
            if item.language:
                kwargs["language"] = item.language
            self._speak_fn(**kwargs)
        except Exception as exc:
            logger.warning("TTS dispatch failed: %s", exc)
        finally:
            self.tts_active.clear()
            if self._tts_state_callback is not None:
                try:
                    self._tts_state_callback(False)
                except Exception:
                    pass
            with self._lock:
                self._current_item = None


__all__ = ["SpeechArbiter", "SpeechItem", "SpeechPriority"]
