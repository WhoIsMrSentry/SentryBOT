from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, Optional
from .pcm import PCM

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


class PCM:  # type: ignore[no-redef]
    pass


class Pyttsx3Backend(TTSBackend):
    def __init__(self, cfg: TTSConfig):
        try:
            import pyttsx3  # type: ignore
        except Exception as e:
            raise RuntimeError("pyttsx3 not installed. Add to requirements or choose 'dummy' engine.") from e
        self.engine = pyttsx3.init()
        if cfg.voice:
            self.engine.setProperty('voice', cfg.voice)
        self.engine.setProperty('rate', cfg.rate)
        self.engine.setProperty('volume', cfg.volume)
        self.samplerate = cfg.samplerate

    def synthesize(self, text: str):
        # pyttsx3 doğrudan PCM verisi döndürmez; workaround: temp wav'e yazıp geri oku.
        import tempfile, os
        import soundfile as sf
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            tmp = os.path.join(d, "out.wav")
            self.engine.save_to_file(text, tmp)
            self.engine.runAndWait()
            data, sr = sf.read(tmp, dtype='float32')
            if data.ndim == 1:
                ch = 1
            else:
                ch = data.shape[1]
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


class TextToSpeech:
    def __init__(self, cfg: Dict):
        tcfg = TTSConfig(
            engine=str(cfg.get("engine", "pyttsx3")),
            language=str(cfg.get("language", "tr")),
            voice=cfg.get("voice"),
            rate=int(cfg.get("rate", 170)),
            volume=float(cfg.get("volume", 1.0)),
            samplerate=int(cfg.get("samplerate", 22050)),
        )
        if tcfg.engine == "piper":
            self.backend = PiperBackend(tcfg, cfg.get("piper", {}))
        elif tcfg.engine == "pyttsx3":
            try:
                self.backend: TTSBackend = Pyttsx3Backend(tcfg)
            except Exception as e:
                logger.warning("pyttsx3 unavailable, falling back to dummy: %s", e)
                self.backend = DummyBackend(tcfg)
        else:
            self.backend = DummyBackend(tcfg)

    def synthesize(self, text: str):
        return self.backend.synthesize(text)
