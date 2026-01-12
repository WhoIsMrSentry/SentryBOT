from __future__ import annotations
import copy
import logging
from dataclasses import dataclass
from typing import Dict, Optional
import threading
from .pcm import PCM

import io

import requests

logger = logging.getLogger("speak.tts")


@dataclass
class TTSConfig:
    engine: str = "pyttsx3"  # pyttsx3 | dummy
    language: str = "tr"
    voice: Optional[str] = None
    rate: int = 170
    volume: float = 1.0
    samplerate: int = 22050


class TTSBackend:
    def synthesize(self, text: str):  # returns PCM
        raise NotImplementedError


def _wav_bytes_to_pcm(wav_bytes: bytes) -> PCM:
    import numpy as np
    import soundfile as sf

    with io.BytesIO(wav_bytes) as f:
        data, sr = sf.read(f, dtype="float32")
    ch = 1 if getattr(data, "ndim", 1) == 1 else int(data.shape[1])
    if isinstance(data, np.ndarray) and data.dtype != np.float32:
        data = data.astype(np.float32)
    return PCM(data=data, samplerate=int(sr), channels=ch)
class Pyttsx3Backend(TTSBackend):
    def __init__(self, cfg: TTSConfig):
        try:
            import pyttsx3  # type: ignore
        except Exception as e:
            raise RuntimeError("pyttsx3 not installed. Add to requirements or choose 'dummy' engine.") from e
        self.cfg = cfg
        self.samplerate = cfg.samplerate
        self._lock = threading.Lock()

    def _make_engine(self):
        import pyttsx3  # type: ignore
        engine = pyttsx3.init()
        if self.cfg.voice:
            engine.setProperty('voice', self.cfg.voice)
        engine.setProperty('rate', self.cfg.rate)
        engine.setProperty('volume', self.cfg.volume)
        return engine

    def synthesize(self, text: str):
        # pyttsx3 doğrudan PCM verisi döndürmez; temp wav'e yazıp geri okuruz.
        import tempfile, os
        import soundfile as sf
        import numpy as np
        with self._lock:
            engine = self._make_engine()
            with tempfile.TemporaryDirectory() as d:
                tmp = os.path.join(d, "out.wav")
                engine.save_to_file(text, tmp)
                engine.runAndWait()
                engine.stop()
                data, sr = sf.read(tmp, dtype='float32')
        ch = 1 if data.ndim == 1 else data.shape[1]
        return PCM(data=data, samplerate=sr, channels=ch)


class DummyBackend(TTSBackend):
    def __init__(self, cfg: TTSConfig):
        self.samplerate = cfg.samplerate

    def synthesize(self, text: str):
        # Basit bir placeholder: kısa bir beep dizisi üret
        import numpy as np
        sr = self.samplerate
        secs = max(0.2, min(1.0, len(text) * 0.03))
        t = np.linspace(0, secs, int(sr * secs), endpoint=False)
        freq = 440.0
        data = 0.2 * np.sin(2 * np.pi * freq * t).astype(np.float32)
        return PCM(data=data, samplerate=sr, channels=1)


class PiperBackend(TTSBackend):
    """Piper TTS subprocess backend.

    Config fields:
      - model_path: .onnx veya .onnx.gz
      - bin_path: piper ikili yolu (varsayılan: 'piper')
      - speaker: opsiyonel speaker id
      - length_scale, noise_scale, noise_w: opsiyonel parametreler
      - samplerate: beklenen örnekleme
    """
    def __init__(self, cfg: TTSConfig, piper_cfg: Dict):
        self.bin_path = str(piper_cfg.get("bin_path", "piper"))
        self.model_path = piper_cfg.get("model_path")
        if not self.model_path:
            raise ValueError("piper.model_path is required")
        self.samplerate = int(piper_cfg.get("samplerate", cfg.samplerate))
        self.speaker = piper_cfg.get("speaker")
        self.length_scale = piper_cfg.get("length_scale")
        self.noise_scale = piper_cfg.get("noise_scale")
        self.noise_w = piper_cfg.get("noise_w")

    def synthesize(self, text: str):
        import subprocess, json, tempfile, os
        import soundfile as sf
        # Piper stdin->wav stdout; bazı kurulumlarda -w ile dosyaya yazmak daha stabil.
        with tempfile.TemporaryDirectory() as d:
            wav_path = os.path.join(d, "out.wav")
            cmd = [self.bin_path, "-m", self.model_path, "-w", wav_path]
            if self.speaker is not None:
                cmd += ["-s", str(self.speaker)]
            if self.length_scale is not None:
                cmd += ["-l", str(self.length_scale)]
            if self.noise_scale is not None:
                cmd += ["-n", str(self.noise_scale)]
            if self.noise_w is not None:
                cmd += ["-e", str(self.noise_w)]
            proc = subprocess.run(cmd, input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                raise RuntimeError(f"piper failed: {proc.stderr.decode('utf-8', 'ignore')}")
            data, sr = sf.read(wav_path, dtype='float32')
            ch = 1 if data.ndim == 1 else data.shape[1]
            return PCM(data=data, samplerate=sr, channels=ch)


class XTTSHttpBackend(TTSBackend):
    """XTTS via external local HTTP service.

    This backend is designed to let XTTS run in a separate Python env (often with CUDA),
    while SentryBOT gateway keeps its own env lightweight.

    Expected endpoint:
      - POST {endpoint} (default: http://127.0.0.1:5002/synthesize)
      - JSON: { text, speaker_wav?, language? }
      - Response: audio/wav bytes
    """

    def __init__(self, cfg: TTSConfig, xtts_cfg: Dict):
        self.samplerate = int(xtts_cfg.get("samplerate", cfg.samplerate))
        self.endpoint = str(xtts_cfg.get("endpoint", "http://127.0.0.1:5002/synthesize")).strip()
        self.timeout = float(xtts_cfg.get("timeout", 120.0))
        self.default_speaker_wav = xtts_cfg.get("speaker_wav")
        self.default_language = str(xtts_cfg.get("language", cfg.language))

        if not self.endpoint:
            raise ValueError("xtts.endpoint is required")

    def synthesize(self, text: str, speaker_wav: Optional[str] = None, language: Optional[str] = None) -> PCM:
        payload: Dict[str, object] = {
            "text": text,
            "language": language or self.default_language,
        }
        wav = speaker_wav or self.default_speaker_wav
        if wav:
            payload["speaker_wav"] = wav

        resp = requests.post(self.endpoint, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return _wav_bytes_to_pcm(resp.content)


class TextToSpeech:
    def __init__(self, cfg: Dict):
        self._base_cfg = copy.deepcopy(cfg)
        self.backend = self._build_backend(self._base_cfg)

    def _build_backend(self, cfg: Dict) -> TTSBackend:
        tcfg = TTSConfig(
            engine=str(cfg.get("engine", "pyttsx3")),
            language=str(cfg.get("language", "tr")),
            voice=cfg.get("voice"),
            rate=int(cfg.get("rate", 170)),
            volume=float(cfg.get("volume", 1.0)),
            samplerate=int(cfg.get("samplerate", 22050)),
        )
        if tcfg.engine == "piper":
            return PiperBackend(tcfg, cfg.get("piper", {}))
        if tcfg.engine == "xtts":
            return XTTSHttpBackend(tcfg, cfg.get("xtts", {}))
        if tcfg.engine == "pyttsx3":
            try:
                return Pyttsx3Backend(tcfg)
            except Exception as e:
                logger.warning("pyttsx3 unavailable, falling back to dummy: %s", e)
                return DummyBackend(tcfg)
        return DummyBackend(tcfg)

    def _merge_overrides(self, overrides: Dict | None) -> Optional[Dict]:
        if not overrides:
            return None
        merged = copy.deepcopy(self._base_cfg)
        if "piper" in overrides:
            merged["piper"] = {**merged.get("piper", {}), **overrides.get("piper", {})}
        if "xtts" in overrides:
            merged["xtts"] = {**merged.get("xtts", {}), **overrides.get("xtts", {})}
        for key, value in overrides.items():
            if key == "piper":
                continue
            if key == "xtts":
                continue
            merged[key] = value
        return merged

    def synthesize(self, text: str, overrides: Optional[Dict] = None):
        if overrides:
            cfg = self._merge_overrides(overrides)
            backend = self._build_backend(cfg or self._base_cfg)
            if isinstance(backend, XTTSHttpBackend):
                speaker_wav = overrides.get("speaker_wav") if isinstance(overrides, dict) else None
                language = overrides.get("language") if isinstance(overrides, dict) else None
                return backend.synthesize(text, speaker_wav=speaker_wav, language=language)
            return backend.synthesize(text)
        return self.backend.synthesize(text)
