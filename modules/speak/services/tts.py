from __future__ import annotations
import copy
import logging
from dataclasses import dataclass
from typing import Dict, Optional
import threading
from pathlib import Path
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
        self.model_path = str(piper_cfg.get("model_path") or "").strip()
        if not self.model_path:
            raise ValueError("piper.model_path is required")
        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"piper.model_path not found: {self.model_path}")
        self.config_path = str(piper_cfg.get("config_path") or f"{self.model_path}.json").strip()
        if self.config_path and not Path(self.config_path).exists():
            logger.warning("piper model config not found: %s", self.config_path)
        self.samplerate = int(piper_cfg.get("samplerate", cfg.samplerate))
        self.speaker = piper_cfg.get("speaker")
        self.length_scale = piper_cfg.get("length_scale")
        self.noise_scale = piper_cfg.get("noise_scale")
        self.noise_w = piper_cfg.get("noise_w")

    def synthesize(self, text: str):
        import subprocess, tempfile, os
        import soundfile as sf

        def _append_long_options(cmd: list[str]) -> list[str]:
            out = list(cmd)
            if self.config_path and os.path.exists(self.config_path):
                out += ["--config", self.config_path]
            if self.speaker is not None:
                out += ["--speaker", str(self.speaker)]
            if self.length_scale is not None:
                out += ["--length_scale", str(self.length_scale)]
            if self.noise_scale is not None:
                out += ["--noise_scale", str(self.noise_scale)]
            if self.noise_w is not None:
                out += ["--noise_w", str(self.noise_w)]
            return out

        def _append_short_options(cmd: list[str]) -> list[str]:
            out = list(cmd)
            if self.speaker is not None:
                out += ["-s", str(self.speaker)]
            if self.length_scale is not None:
                out += ["-l", str(self.length_scale)]
            if self.noise_scale is not None:
                out += ["-n", str(self.noise_scale)]
            if self.noise_w is not None:
                out += ["-e", str(self.noise_w)]
            return out

        def _load_wav_from_path(path: str) -> Optional[PCM]:
            if not os.path.exists(path):
                return None
            if os.path.getsize(path) <= 0:
                return None
            data, sr = sf.read(path, dtype='float32')
            ch = 1 if data.ndim == 1 else data.shape[1]
            return PCM(data=data, samplerate=sr, channels=ch)

        stdin_text = (text or "").strip()
        if not stdin_text:
            raise ValueError("text is empty")

        with tempfile.TemporaryDirectory() as d:
            wav_path = os.path.join(d, "out.wav")
            cmd_variants = [
                _append_long_options([self.bin_path, "--model", self.model_path, "--output_file", wav_path]),
                _append_short_options([self.bin_path, "-m", self.model_path, "-w", wav_path]),
            ]

            last_error = ""
            for cmd in cmd_variants:
                proc = subprocess.run(
                    cmd,
                    input=(stdin_text + "\n").encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stderr_txt = proc.stderr.decode("utf-8", "ignore").strip()

                if proc.returncode == 0:
                    try:
                        pcm = _load_wav_from_path(wav_path)
                        if pcm is not None:
                            return pcm
                    except Exception as exc:
                        last_error = f"wav read failed: {exc}"

                    if proc.stdout:
                        try:
                            return _wav_bytes_to_pcm(proc.stdout)
                        except Exception as exc:
                            last_error = f"stdout wav parse failed: {exc}"
                    else:
                        last_error = "piper finished without producing readable WAV output"
                else:
                    last_error = f"exit={proc.returncode}; stderr={stderr_txt or '<empty>'}"

            raise RuntimeError(f"piper failed: {last_error}")


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
