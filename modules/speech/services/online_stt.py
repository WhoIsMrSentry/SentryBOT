"""Online STT (Speech-to-Text) module for high-accuracy cloud transcription."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import wave
from typing import Optional

import requests

logger = logging.getLogger("speech.online_stt")


def pcm16_to_wav(pcm_bytes: bytes, samplerate: int = 16000, channels: int = 1) -> bytes:
    """Convert raw 16-bit PCM bytes to WAV format."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(samplerate)
        wav.writeframes(pcm_bytes)
    return buf.getvalue()


def transcribe_gemini(
    pcm_bytes: bytes,
    api_key: Optional[str] = None,
    model: str = "gemini-2.0-flash",
    target_lang: str = "tr",
    timeout_s: float = 4.0,
) -> Optional[str]:
    """Transcribe audio PCM bytes using Google Gemini multimodal audio API."""
    key = str(api_key or os.environ.get("GOOGLE_API_KEY", "")).strip()
    if not key or len(pcm_bytes) < 3200:  # < 100ms
        return None

    try:
        wav_bytes = pcm16_to_wav(pcm_bytes, samplerate=16000, channels=1)
        b64_audio = base64.b64encode(wav_bytes).decode("utf-8")

        prompt = (
            "Transcribe this spoken audio recording verbatim. "
            "The speaker is speaking Turkish (or English). "
            "Output ONLY the plain transcribed words. Do not add quotes, markdown, or explanations."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/wav",
                                "data": b64_audio,
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 64,
            },
        }

        resp = requests.post(url, json=payload, timeout=timeout_s)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text = str(parts[0].get("text", "")).strip()
                    if text:
                        logger.info("Gemini STT transcribed: %r", text)
                        return text
        else:
            logger.debug("Gemini STT request returned HTTP %d: %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.debug("Gemini STT transcription error: %s", exc)

    return None
