from __future__ import annotations

from datetime import datetime
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("autonomy.client")


class ClientSpeechMixin:
    """Speech, Speak (TTS), STT, and Ollama chat methods for ServiceClient."""

    urls: Dict[str, str]
    speech_quiet_cfg: Dict[str, Any]
    speech_stream_cfg: Dict[str, Any]
    request_timeouts: Dict[str, Any]
    _post: Callable[..., Any]
    _get: Callable[..., Any]
    _async_post: Callable[..., Any]
    _async_get: Callable[..., Any]

    @staticmethod
    def _parse_hhmm(value: Any) -> tuple[int, int] | None:
        text = str(value or "").strip()
        parts = text.split(":")
        if len(parts) != 2:
            return None
        try:
            hh = int(parts[0])
            mm = int(parts[1])
        except Exception:
            return None
        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            return None
        return hh, mm

    def _quiet_hours_active(self) -> bool:
        cfg = self.speech_quiet_cfg
        if not bool(cfg.get("enabled", False)):
            return False
        start = self._parse_hhmm(cfg.get("start", "23:00"))
        end = self._parse_hhmm(cfg.get("end", "07:00"))
        if start is None or end is None:
            return False
        now_dt = datetime.now()
        now = now_dt.hour * 60 + now_dt.minute
        start_m = start[0] * 60 + start[1]
        end_m = end[0] * 60 + end[1]
        if start_m == end_m:
            return True
        if start_m < end_m:
            return start_m <= now < end_m
        return now >= start_m or now < end_m

    def speak(self, text: str, tone=None, engine=None, language=None, trace_id=None) -> Any:
        payload = self._build_speak_payload(
            text, tone=tone, engine=engine, language=language, trace_id=trace_id,
        )
        return self._post("speak", "/say", payload)

    def _build_speak_payload(self, text: str, tone=None, engine=None, language=None, trace_id=None) -> Dict[str, Any]:
        text_value = str(text or "")
        if self._quiet_hours_active():
            max_chars = int(self.speech_quiet_cfg.get("max_chars", 120))
            prefix = str(self.speech_quiet_cfg.get("prefix", "")).strip()
            if max_chars > 0 and len(text_value) > max_chars:
                text_value = text_value[: max_chars - 3].rstrip() + "..."
            if prefix:
                text_value = f"{prefix}{text_value}"
            if tone is None:
                tone = self.speech_quiet_cfg.get("tone", "calm")
        payload = {"text": text_value}
        if tone:
            payload["tone"] = tone
        if engine:
            payload["engine"] = engine
        if language:
            payload["language"] = str(language)
        if trace_id:
            payload["trace_id"] = str(trace_id)
        return payload

    def speak_stream(self, text: str, tone=None, engine=None, language=None, max_chunk_chars=None, trace_id=None) -> Any:
        payload = self._build_speak_payload(
            text, tone=tone, engine=engine, language=language, trace_id=trace_id,
        )
        if not str(payload.get("text", "")).strip():
            return {"ok": False, "error": "text is empty"}
        if max_chunk_chars is not None:
            payload["max_chunk_chars"] = int(max_chunk_chars)
        elif self.speech_stream_cfg.get("stream_max_chunk_chars"):
            payload["max_chunk_chars"] = int(self.speech_stream_cfg.get("stream_max_chunk_chars"))

        start_timeout = float(self.request_timeouts.get("speak_stream_start_s", 4.0))
        resp = self._post("speak", "/say_stream", payload, timeout_s=start_timeout)
        if not resp or not resp.get("ok"):
            return self.speak(text, tone=tone, engine=engine, language=language, trace_id=trace_id)

        job_id = str(resp.get("job_id") or "").strip()
        if not job_id:
            return resp

        poll_s = float(self.speech_stream_cfg.get("stream_poll_interval_s", 0.12))
        max_wait = float(self.speech_stream_cfg.get("stream_max_wait_s", 90.0))
        deadline = time.time() + max_wait
        while time.time() < deadline:
            status = self._get("speak", f"/jobs/{job_id}", timeout_s=2.0)
            if not isinstance(status, dict):
                time.sleep(poll_s)
                continue
            job = status.get("job") if isinstance(status.get("job"), dict) else status
            state = str(job.get("status") or "").strip().lower()
            if state in {"done", "failed", "interrupted"}:
                return {"ok": state != "failed", "status": state, "job": job, "job_id": job_id}
            time.sleep(poll_s)
        return {"ok": False, "error": "stream_timeout", "job_id": job_id}

    def speak_preferred(self, text: str, tone=None, engine=None, language=None, trace_id=None) -> Any:
        if bool(self.speech_stream_cfg.get("use_stream_tts", False)):
            return self.speak_stream(
                text, tone=tone, engine=engine, language=language, trace_id=trace_id,
            )
        return self.speak(text, tone=tone, engine=engine, language=language, trace_id=trace_id)

    def chat(self, query: str, apply_actions: bool | None = None, source_lang: str | None = None, response_lang: str | None = None) -> Any:
        params = {"query": query}
        if apply_actions is not None:
            params["apply_actions"] = str(bool(apply_actions)).lower()
        if source_lang:
            params["source_lang"] = str(source_lang)
        if response_lang:
            params["response_lang"] = str(response_lang)
        timeout = float(self.request_timeouts.get("ollama_chat_s", 20.0))
        return self._post("ollama", "/chat", None, params=params, timeout_s=timeout)

    def warmup_ollama(self) -> Any:
        timeout = float(self.request_timeouts.get("ollama_warmup_s", 2.5))
        return self._post("ollama", "/warmup", timeout_s=timeout)

    def get_speech_direction(self) -> Any:
        return self._get("speech", "/direction")

    def get_last_speech(self) -> Any:
        return self._get("speech", "/last")

    def set_speech_tracking(self, enabled: bool) -> Any:
        endpoint = "/track/start" if enabled else "/track/stop"
        return self._post("speech", endpoint)

    def set_stt_suppressed(self, suppressed: bool) -> Any:
        return self._post("speech", "/stt/suppress", {"enabled": bool(suppressed)}, timeout_s=0.25)

    def stop_speaking(self) -> Any:
        return self._post("speak", "/stop", timeout_s=0.35)

    def start_speech_listening(self) -> Any:
        return self._post("speech", "/start", timeout_s=0.35)

    def translate(self, text: str, source_lang: str, target_lang: str) -> Any:
        params = {
            "text": str(text or ""),
            "source_lang": str(source_lang or "auto"),
            "target_lang": str(target_lang or "en"),
        }
        return self._post("ollama", "/translate", None, params=params)

    def select_persona(self, name: str) -> Any:
        return self._post("ollama", "/persona/select", {"name": name})

    async def async_speak(self, text: str, tone: str = "neutral",
                          language: str = "tr", pitch_shift: float = 0.0,
                          speed: float = 1.0) -> dict:
        return await self._async_post(
            "speak", "/say",
            json={
                "text": text,
                "tone": tone,
                "language": language,
                "pitch_shift": pitch_shift,
                "speed": speed,
            },
            timeout=4.0,
        )

    async def async_chat(self, message: str, source_lang: str = "tr",
                         response_lang: str = "tr") -> dict:
        return await self._async_post(
            "ollama", "/chat",
            params={
                "query": message,
                "source_lang": source_lang,
                "response_lang": response_lang,
            },
            timeout=25.0,
        )
