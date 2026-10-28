"""xSpeakerIdService -- speaker voiceprint enrollment + identification (MVP).

Pipeline-independent by design: callers feed mono PCM (float or int16) plus the
capture samplerate; on the Pi the brain can pipe VAD speech segments into
`identify` to enrich `last_speaker` with a voice-identity hint.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .config_loader import load_config
from .services.voiceprint import VoiceprintEmbedder
from .services.voiceprint_store import VoiceprintStore


class SpeakerIdError(RuntimeError):
    pass


class SpeakerIdService:
    def __init__(self, config_path: str | None = None) -> None:
        self.cfg = load_config(config_path)
        self.enabled = bool(self.cfg.get("enabled", True))
        self.threshold = self.cfg.get("threshold") or {}
        self.sim_min = float(self.threshold.get("similarity", 0.75))
        self.margin_min = float(self.threshold.get("margin", 0.05))
        self.enroll_min = int(self.cfg.get("enroll_min_frames", 30))   # voiced windows needed
        self.embedder = VoiceprintEmbedder(
            bands=int(self.cfg.get("bands", 20)),
            min_energy_rms=float(self.cfg.get("min_energy_rms", 0.004)),
        )
        self.store = VoiceprintStore(
            str(self.cfg.get("store_path", "data/speaker_id.json")),
            max_profiles=int(self.cfg.get("max_profiles", 16)),
        )

    # ------------------------------------------------------------------ API
    def enroll_speaker(self, name: str, speaker_pcm: Any, samplerate: int, replace: bool = False) -> Dict[str, Any]:
        if not self.enabled:
            raise SpeakerIdError("speaker_id disabled")
        vec = self.embedder.embed(speaker_pcm, samplerate)
        if vec is None:
            raise SpeakerIdError("clip has too little speech to enroll")
        result = self.store.upsert(name, vec, replace=bool(replace))
        return {"ok": True, "name": name, "samples": result.get("samples", 1), "backend": "voiceprint_mvp"}

    def identify(self, speaker_pcm: Any, samplerate: int) -> Dict[str, Any]:
        if not self.enabled:
            raise SpeakerIdError("speaker_id disabled")
        vec = self.embedder.embed(speaker_pcm, samplerate)
        if vec is None:
            return {"ok": True, "known": False, "reason": "too_little_speech", "samplerate": samplerate}
        profiles = self.store.all()
        if not profiles:
            return {"ok": True, "known": False, "reason": "no_profiles", "backend": "voiceprint_mvp"}
        scores = []
        for key, entry in profiles.items():
            other = entry.get("vec") or []
            if not other:
                continue
            scores.append((self._cosine(vec, other), key))
        if not scores:
            return {"ok": True, "known": False, "reason": "no_valid_profiles", "backend": "voiceprint_mvp"}
        scores.sort(reverse=True)
        best_sim, best_name = scores[0]
        second_sim = scores[1][0] if len(scores) > 1 else -1.0
        margin = best_sim - second_sim
        if best_sim < self.sim_min or margin < self.margin_min:
            return {
                "ok": True, "known": False, "candidate": best_name,
                "similarity": round(best_sim, 4), "margin": round(margin, 4),
                "backend": "voiceprint_mvp",
            }
        return {
            "ok": True, "known": True, "name": best_name,
            "similarity": round(best_sim, 4), "margin": round(margin, 4),
            "backend": "voiceprint_mvp",
        }

    def forget(self, name: str) -> Dict[str, Any]:
        if not self.enabled:
            raise SpeakerIdError("speaker_id disabled")
        return self.store.forget(name)

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.enabled,
            "backend": "voiceprint_mvp",
            "profiles": self.store.names(),
            "profile_count": self.store.count(),
            "threshold": {"similarity": self.sim_min, "margin": self.margin_min},
        }

    def health(self) -> Dict[str, Any]:
        st = self.status()
        st["store_file"] = str(self.store.path)
        st["store_ok"] = self.store.path.is_file() or self.store.count() == 0
        return st

    @staticmethod
    def _cosine(a: Any, b: Any) -> float:
        import numpy as np

        va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
        if va.size == 0 or va.size != vb.size:
            return -1.0
        na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if na == 0.0 or nb == 0.0:
            return -1.0
        return float(np.dot(va, vb) / (na * nb))


def get_default() -> Optional[SpeakerIdService]:
    """Singleton helper so callers share one store file handle lifecycle."""
    global _DEFAULT          # type: ignore[name-defined]
    try:
        _DEFAULT             # noqa: F821
    except NameError:
        globals()["_DEFAULT"] = SpeakerIdService()
    return globals()["_DEFAULT"]
