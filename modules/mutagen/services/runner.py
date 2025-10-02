from __future__ import annotations
import subprocess
from typing import Dict, Any, List


class MutagenRunner:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def _has_cli(self) -> bool:
        try:
            subprocess.run(["mutagen", "version"], capture_output=True, text=True, timeout=5)
            return True
        except Exception:
            return False

    def status(self) -> Dict[str, Any]:
        if not self._has_cli():
            return {"ok": False, "error": "mutagen not installed"}
        proc = subprocess.run(["mutagen", "sync", "list", "--json"], capture_output=True, text=True)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def start(self) -> Dict[str, Any]:
        if not self._has_cli():
            return {"ok": False, "error": "mutagen not installed"}
        results: List[Dict[str, Any]] = []
        pairs = self.cfg.get("pairs", []) or []
        opts = self.cfg.get("opts", {})
        for p in pairs:
            alpha = str(p.get("alpha"))
            beta = str(p.get("beta"))
            name = str(p.get("name", "pair"))
            mode = str(p.get("mode", opts.get("sync_mode", "two-way-resolved")))
            args = ["mutagen", "sync", "create", "--name", name, "--sync-mode", mode]
            ignore = opts.get("ignore", [])
            for patt in ignore:
                args += ["--ignore", str(patt)]
            args += [alpha, beta]
            proc = subprocess.run(args, capture_output=True, text=True)
            results.append({
                "name": name,
                "ok": proc.returncode == 0,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            })
        return {"ok": all(r.get("ok") for r in results), "results": results}

    def stop(self) -> Dict[str, Any]:
        if not self._has_cli():
            return {"ok": False, "error": "mutagen not installed"}
        proc = subprocess.run(["mutagen", "sync", "terminate", "--all"], capture_output=True, text=True)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def rescan(self) -> Dict[str, Any]:
        if not self._has_cli():
            return {"ok": False, "error": "mutagen not installed"}
        proc = subprocess.run(["mutagen", "sync", "flush", "--all"], capture_output=True, text=True)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}
