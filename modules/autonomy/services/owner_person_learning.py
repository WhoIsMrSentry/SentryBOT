
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

class OwnerPersonLearning:
    DEFAULTS = {"enabled": True, "profile_path": "data/owner_profile.json", "min_confidence": 0.55}
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, client: Any = None, memory: Any = None) -> None:
        self.cfg = dict(self.DEFAULTS)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self.client = client; self.memory = memory
        self.path = Path(str(self.cfg.get("profile_path") or self.DEFAULTS["profile_path"]))
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"owners": [], "updated_ts": time.time()}, ensure_ascii=False, indent=2), encoding="utf-8")
        self._last: Dict[str, Any] = {"ok": True, "reason": "never_identified"}
    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"owners": []}
        except Exception:
            return {"owners": []}
    def _save(self, data: Dict[str, Any]) -> None:
        data["updated_ts"] = time.time(); self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    def status(self) -> Dict[str, Any]:
        data = self._load(); return {"ok": True, "available": True, "profile_path": str(self.path), "owners": data.get("owners", []), "last": dict(self._last)}
    def learn(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        name = str(body.get("name") or body.get("person") or body.get("owner_name") or "owner").strip()
        owner_id = str(body.get("id") or body.get("owner_id") or name.lower().replace(" ", "_")).strip()
        record = {"id": owner_id, "name": name, "aliases": [str(a) for a in body.get("aliases", [])] if isinstance(body.get("aliases"), list) else [], "confidence": max(0.0, min(1.0, float(body.get("confidence", 0.75)))), "learned_ts": time.time(), "last_seen": time.time(), "track_hint": body.get("track") if isinstance(body.get("track"), dict) else self._current_target(), "details": body.get("details") if isinstance(body.get("details"), dict) else {}}
        data = self._load(); owners = [x for x in data.get("owners", []) if isinstance(x, dict) and x.get("id") != owner_id]; owners.append(record); data["owners"] = owners; self._save(data); self._remember_world(record)
        return {"ok": True, "available": True, "owner": record}
    def identify(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}; target = body.get("target") if isinstance(body.get("target"), dict) else self._current_target()
        owners = [x for x in self._load().get("owners", []) if isinstance(x, dict)]
        if not owners:
            self._last = {"ok": True, "available": True, "identified": False, "reason": "no_owner_learned", "target": target}; return dict(self._last)
        label = str((target or {}).get("label") or (target or {}).get("name") or (target or {}).get("person") or "").lower()
        best = None; score = 0.0
        for owner in owners:
            names = [str(owner.get("name") or "").lower(), str(owner.get("id") or "").lower()] + [str(a).lower() for a in owner.get("aliases", [])]
            local = float(owner.get("confidence", 0.0))
            if label and any(n and n in label for n in names):
                local = max(local, 0.85)
            if local > score:
                score = local; best = owner
        identified = bool(best and score >= float(self.cfg.get("min_confidence", 0.55)))
        self._last = {"ok": True, "available": True, "identified": identified, "owner": best if identified else None, "score": round(score, 3), "target": target}
        return dict(self._last)
    def _current_target(self) -> Dict[str, Any]:
        if self.client is None:
            return {}
        try:
            data = self.client._get("camera", "/tracking/target", timeout_s=0.6)
            if isinstance(data, dict):
                target = data.get("target") if isinstance(data.get("target"), dict) else data
                return target if isinstance(target, dict) else {}
        except Exception:
            pass
        return {}
    def _remember_world(self, owner: Dict[str, Any]) -> None:
        if self.memory is None:
            return
        try:
            self.memory.observe({"kind": "person", "name": owner.get("name") or owner.get("id"), "summary": "Known owner/person: " + str(owner.get("name") or owner.get("id")), "confidence": owner.get("confidence", 0.75), "salience": 0.9, "tags": ["person", "owner"], "details": owner}, source="owner_learning")
        except Exception:
            pass

__all__ = ["OwnerPersonLearning"]
