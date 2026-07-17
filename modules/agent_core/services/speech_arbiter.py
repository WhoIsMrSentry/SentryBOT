from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agent.speech_arbiter")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str, max_chars: int = 160, max_chunks: int = 8) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    chunks: List[str] = []
    for part in [item.strip() for item in _SENTENCE_SPLIT_RE.split(raw) if item.strip()]:
        words = part.split()
        buffer: List[str] = []
        for word in words:
            candidate = " ".join(buffer + [word])
            if buffer and len(candidate) > max_chars:
                chunks.append(" ".join(buffer))
                buffer = [word]
            else:
                buffer.append(word)
        if buffer:
            chunks.append(" ".join(buffer))
    if len(chunks) > max_chunks:
        chunks = chunks[: max_chunks - 1] + [" ".join(chunks[max_chunks - 1 :])]
    return chunks


class SpeechPriority:
    SAFETY = 95
    FINAL_RESPONSE = 60
    PROGRESS = 30
    IDLE = 15


@dataclass
class SpeechItem:
    text: str
    priority: int = SpeechPriority.PROGRESS
    category: str = "progress"
    cancel_token: str = ""
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    created_at: float = field(default_factory=time.time)
    max_age_s: float = 10.0
    language: str = ""
    tone: Optional[Dict[str, Any]] = None
    trace_id: str = ""

    @property
    def expired(self) -> bool:
        return time.time() - self.created_at > self.max_age_s


class SpeechArbiter:
    def __init__(self, speak_fn: Optional[Callable[..., Any]] = None, max_queue_size: int = 10) -> None:
        self._speak_fn = speak_fn
        self._max_queue = max(3, int(max_queue_size))
        self._lock = threading.RLock()
        self._queue: List[SpeechItem] = []
        self._processing = threading.Event()
        self._stop_event = threading.Event()
        self._interrupt_flag = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._current_item: Optional[SpeechItem] = None
        self._tts_state_callback: Optional[Callable[[bool], Any]] = None
        self._stop_playback_fn: Optional[Callable[[], Any]] = None
        self._recent_texts: Dict[str, float] = {}
        self._dedup_window_s = 5.0
        self.tts_active = threading.Event()

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, daemon=True, name="speech_arbiter")
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._processing.set()
        if self._worker:
            self._worker.join(timeout=2.0)

    def set_speak_fn(self, fn: Callable[..., Any]) -> None:
        self._speak_fn = fn

    def set_tts_state_callback(self, fn: Callable[[bool], Any]) -> None:
        self._tts_state_callback = fn

    def set_stop_playback_fn(self, fn: Callable[[], Any]) -> None:
        self._stop_playback_fn = fn

    def interrupt_all(self) -> int:
        self._interrupt_flag.set()
        cleared = self.clear_queue()
        if self._stop_playback_fn:
            try:
                self._stop_playback_fn()
            except Exception:
                logger.debug("stop playback failed", exc_info=True)
        self._set_tts_active(False)
        with self._lock:
            self._current_item = None
        return cleared

    def enqueue(
        self,
        text: str,
        priority: int = SpeechPriority.PROGRESS,
        category: str = "progress",
        cancel_token: str = "",
        language: str = "",
        tone: Optional[Dict[str, Any]] = None,
        max_age_s: float = 10.0,
        trace_id: str = "",
    ) -> Optional[str]:
        value = str(text or "").strip()
        if not value:
            return None
        now = time.time()
        key = value[:80].lower()
        with self._lock:
            if now - self._recent_texts.get(key, 0.0) < self._dedup_window_s:
                return None
            self._queue = [item for item in self._queue if not item.expired]
            item = SpeechItem(
                text=value,
                priority=int(priority),
                category=str(category),
                cancel_token=str(cancel_token or ""),
                language=str(language or ""),
                tone=dict(tone) if isinstance(tone, dict) else None,
                max_age_s=float(max_age_s),
                trace_id=str(trace_id or ""),
            )
            if len(self._queue) >= self._max_queue:
                lowest = min(self._queue, key=lambda queued: queued.priority)
                if item.priority <= lowest.priority:
                    return None
                self._queue.remove(lowest)
            self._queue.append(item)
        self._processing.set()
        return item.item_id

    def enqueue_progress(
        self,
        text: str,
        cancel_token: str = "",
        language: str = "",
        trace_id: str = "",
    ) -> Optional[str]:
        return self.enqueue(
            text,
            priority=SpeechPriority.PROGRESS,
            category="progress",
            cancel_token=cancel_token,
            language=language,
            max_age_s=8.0,
            trace_id=trace_id,
        )

    def enqueue_final(
        self,
        text: str,
        language: str = "",
        tone: Optional[Dict[str, Any]] = None,
        trace_id: str = "",
    ) -> Optional[str]:
        self.cancel_progress()
        chunks = split_sentences(text)
        first_id: Optional[str] = None
        for index, chunk in enumerate(chunks):
            item_id = self.enqueue_final_chunk(
                chunk,
                index=index,
                language=language,
                tone=tone,
                trace_id=trace_id,
            )
            first_id = first_id or item_id
        return first_id

    def enqueue_final_chunk(
        self,
        text: str,
        index: int = 0,
        language: str = "",
        tone: Optional[Dict[str, Any]] = None,
        trace_id: str = "",
    ) -> Optional[str]:
        return self.enqueue(
            text,
            priority=SpeechPriority.FINAL_RESPONSE,
            category="final",
            cancel_token=f"final:{trace_id}:{index}" if trace_id else f"final:{index}",
            language=language,
            tone=tone,
            max_age_s=45.0,
            trace_id=trace_id,
        )

    def enqueue_safety(self, text: str, trace_id: str = "") -> Optional[str]:
        self.interrupt_all()
        self._interrupt_flag.clear()
        return self.enqueue(
            text,
            priority=SpeechPriority.SAFETY,
            category="safety",
            max_age_s=20.0,
            trace_id=trace_id,
        )

    def cancel_by_token(self, cancel_token: str) -> int:
        token = str(cancel_token or "")
        if not token:
            return 0
        with self._lock:
            before = len(self._queue)
            self._queue = [item for item in self._queue if item.cancel_token != token]
            return before - len(self._queue)

    def cancel_progress(self) -> int:
        with self._lock:
            before = len(self._queue)
            self._queue = [item for item in self._queue if item.category != "progress"]
            return before - len(self._queue)

    def clear_queue(self) -> int:
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    def is_speaking(self) -> bool:
        return self.tts_active.is_set()

    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            current = self._current_item
            return {
                "speaking": self.tts_active.is_set(),
                "queue_size": len(self._queue),
                "current": {
                    "item_id": current.item_id,
                    "category": current.category,
                    "trace_id": current.trace_id,
                    "text": current.text[:80],
                } if current else None,
            }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._processing.wait(timeout=0.5)
            self._processing.clear()
            while not self._stop_event.is_set():
                item = self._pop_next()
                if item is None:
                    break
                self._dispatch(item)

    def _pop_next(self) -> Optional[SpeechItem]:
        with self._lock:
            self._queue = [item for item in self._queue if not item.expired]
            if not self._queue:
                return None
            self._queue.sort(key=lambda item: (-item.priority, item.created_at))
            return self._queue.pop(0)

    def _set_tts_active(self, active: bool) -> None:
        if active:
            self.tts_active.set()
        else:
            self.tts_active.clear()
        if self._tts_state_callback:
            try:
                self._tts_state_callback(active)
            except Exception:
                logger.debug("tts state callback failed", exc_info=True)

    def _dispatch(self, item: SpeechItem) -> None:
        if item.expired or not self._speak_fn:
            return
        if self._interrupt_flag.is_set():
            self._interrupt_flag.clear()
            return

        key = item.text[:80].lower()
        with self._lock:
            self._recent_texts[key] = time.time()
            self._current_item = item
            cutoff = time.time() - self._dedup_window_s * 2
            self._recent_texts = {text: ts for text, ts in self._recent_texts.items() if ts > cutoff}

        self._set_tts_active(True)
        try:
            kwargs: Dict[str, Any] = {"text": item.text}
            if item.tone:
                kwargs["tone"] = item.tone
            if item.language:
                kwargs["language"] = item.language
            if item.trace_id:
                kwargs["trace_id"] = item.trace_id
            self._speak_fn(**kwargs)
        except Exception:
            logger.warning("TTS dispatch failed", exc_info=True)
        finally:
            self._set_tts_active(False)
            with self._lock:
                self._current_item = None


__all__ = ["SpeechArbiter", "SpeechItem", "SpeechPriority", "split_sentences"]
