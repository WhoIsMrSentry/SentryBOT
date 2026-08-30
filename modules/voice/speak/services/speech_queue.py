"""Speech Priority Queue (Merkezi Konuşma Öncelik Kuyruğu).

Konuşma isteklerini önceliklendirerek yarış koşullarını ve birbirinin üstüne konuşmayı önler:
- EMERGENCY (100): Kritik uyarılar, güvenlik ve hata bildirimleri.
- USER_RESPONSE (50): Kullanıcının doğrudan sorusuna verilen cevaplar.
- ALERT (30): Sistem durum güncellemeleri.
- IDLE_CHATTER (10): Boşta kendi kendine konuşma veya ortam yorumları.

Eğer düşük öncelikli bir cümle seslendirilirken yüksek öncelikli bir istek gelirse,
aktif konuşma derhal kesilir (preempt) ve yüksek öncelikli cümle söylenir.
"""

from __future__ import annotations
import heapq
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

class SpeechPriority(IntEnum):
    EMERGENCY = 100
    USER_RESPONSE = 50
    ALERT = 30
    IDLE_CHATTER = 10

@dataclass(order=True)
class SpeechRequest:
    priority: int
    timestamp: float
    text: str = field(compare=False)
    options: Dict[str, Any] = field(default_factory=dict, compare=False)

class SpeechPriorityQueue:
    def __init__(self, stop_callback: Optional[Callable[[], None]] = None) -> None:
        self._lock = threading.Lock()
        self._queue: List[SpeechRequest] = []
        self._current_request: Optional[SpeechRequest] = None
        self._stop_callback = stop_callback

    def submit(
        self,
        text: str,
        priority: int = SpeechPriority.USER_RESPONSE,
        options: Optional[Dict[str, Any]] = None,
    ) -> bool:
        req = SpeechRequest(
            priority=-int(priority),  # heapq min-heap olduğundan yüksek öncelik için eksi
            timestamp=time.time(),
            text=str(text or "").strip(),
            options=dict(options or {}),
        )

        with self._lock:
            # Eğer şu an konuşulan bir şey varsa ve gelen istek daha yüksek öncelikliyse:
            if self._current_request is not None and int(priority) > (-self._current_request.priority):
                if self._stop_callback:
                    try:
                        self._stop_callback()
                    except Exception:
                        pass
                self._current_request = None

            heapq.heappush(self._queue, req)
            return True

    def get_next(self) -> Optional[SpeechRequest]:
        with self._lock:
            if not self._queue:
                self._current_request = None
                return None
            req = heapq.heappop(self._queue)
            self._current_request = req
            return req

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self._current_request = None

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0
