from __future__ import annotations
import hashlib
import hmac
import json
import os
import glob
import subprocess
from typing import Dict, Any, Optional, Tuple


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_versions(db_path: str) -> Dict[str, str]:
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_versions(db_path: str, data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class AvrDudeUploader:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.db_path = str(cfg.get("version_db", "modules/ota/config/versions.json"))
        self.versions = _load_versions(self.db_path)
        self.security_cfg = cfg.get("security", {})
    
    def _check_allowlist(self, sha: str) -> bool:
        """Check if firmware hash is in allowlist (if enabled)."""
        if not self.security_cfg.get("enable_allowlist", False):
            return True
        allowed = self.security_cfg.get("allowed_hashes", [])
        return sha in allowed
    
    def _verify_signature(self, hex_path: str, provided_signature: Optional[str]) -> bool:
        """Verify HMAC-SHA256 signature (if enabled)."""
        if not self.security_cfg.get("enable_signature", False):
            return True
        if not provided_signature:
            return False
        
        secret_key = self.security_cfg.get("secret_key", "")
        if not secret_key:
            return False
        
        with open(hex_path, "rb") as f:
            hex_content = f.read()
        
        expected_sig = hmac.new(
            secret_key.encode(), hex_content, hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_sig, provided_signature)

    def find_artifact(self) -> Optional[str]:
        watch = str(self.cfg.get("watch_dir", "arduino/firmware/xMain/build"))
        pattern = str(self.cfg.get("artifact_glob", "*.hex"))
        matches = sorted(glob.glob(os.path.join(watch, pattern)))
        return matches[-1] if matches else None

    def compute_version(self, path: str) -> Tuple[str, str]:
        sha = _sha256(path)
        return os.path.basename(path), sha

    def already_uploaded(self, name: str, sha: str) -> bool:
        return self.versions.get(name) == sha

    def mark_uploaded(self, name: str, sha: str) -> None:
        self.versions[name] = sha
        _save_versions(self.db_path, self.versions)

    def _avrdude_cmd(self, hex_path: str) -> list[str]:
        board = self.cfg.get("board", {})
        avrd = self.cfg.get("avrdude", {})
        cmd = [str(avrd.get("bin", "avrdude"))]
        if avrd.get("config"):
            cmd += ["-C", str(avrd.get("config"))]
        cmd += ["-v", "-patmega328p"]
        mcu = str(board.get("mcu", "atmega328p"))
        cmd[-1] = f"-p{mcu}"
        programmer = str(board.get("programmer", "arduino"))
        cmd += [f"-c{programmer}"]
        port = str(board.get("port", "/dev/ttyUSB0"))
        cmd += [f"-P{port}"]
        baud = int(board.get("baud", 115200))
        cmd += [f"-b{baud}"]
        extra = avrd.get("extra_flags", [])
        if isinstance(extra, list):
            cmd += [str(x) for x in extra]
        cmd += ["-D", f"-Uflash:w:{hex_path}:i"]
        return cmd

    def upload(self, hex_path: str, signature: Optional[str] = None) -> Dict[str, Any]:
        """Upload firmware with optional security checks.
        
        Args:
            hex_path: Path to .hex file
            signature: Optional HMAC-SHA256 signature (if security.enable_signature is True)
        
        Returns:
            Dict with 'ok', 'returncode', 'stdout', 'stderr', 'cmd', and optional 'security_error'
        """
        # Security checks (non-breaking defaults)
        if self.security_cfg.get("enable_allowlist", False):
            _, sha = self.compute_version(hex_path)
            if not self._check_allowlist(sha):
                return {
                    "ok": False,
                    "security_error": f"Firmware hash {sha} not in allowlist",
                    "returncode": -1,
                }
        
        if self.security_cfg.get("enable_signature", False):
            if not self._verify_signature(hex_path, signature):
                return {
                    "ok": False,
                    "security_error": "Signature verification failed",
                    "returncode": -1,
                }
        
        # Proceed with upload
        cmd = self._avrdude_cmd(hex_path)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            ok = proc.returncode == 0
            return {
                "ok": ok,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
                "cmd": cmd,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


class OTAService:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.uploader = AvrDudeUploader(cfg.get("ota", {}))

    def scan_once(self) -> Dict[str, Any]:
        path = self.uploader.find_artifact()
        if not path:
            return {"ok": True, "found": False}
        name, sha = self.uploader.compute_version(path)
        if self.uploader.already_uploaded(name, sha):
            return {"ok": True, "found": True, "skipped": True, "name": name, "sha": sha}
        res = self.uploader.upload(path)
        if res.get("ok"):
            self.uploader.mark_uploaded(name, sha)
        res.update({"name": name, "sha": sha})
        return res

    def upload_path(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {"ok": False, "error": "file not found"}
        name, sha = self.uploader.compute_version(path)
        if self.uploader.already_uploaded(name, sha):
            return {"ok": True, "skipped": True, "name": name, "sha": sha}
        res = self.uploader.upload(path)
        if res.get("ok"):
            self.uploader.mark_uploaded(name, sha)
        res.update({"name": name, "sha": sha})
        return res

    def versions(self) -> Dict[str, Any]:
        return {"ok": True, "items": self.uploader.versions}

    def clear_versions(self) -> Dict[str, Any]:
        self.uploader.versions = {}
        _save_versions(self.uploader.db_path, self.uploader.versions)
        return {"ok": True}
