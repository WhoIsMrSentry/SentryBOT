"""Background Cloud Backup & Sync Service for SentryBOT.

Handles periodic backup of local databases (social_db, world_memory) and optional images
to a remote HTTP or S3 endpoint. Safely disabled by default.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml

logger = logging.getLogger("autonomy.cloud_backup")

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "cloud_backup.yml"


class CloudBackupSync:
    """Safely synchronizes local database snapshots to a remote cloud endpoint."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = self._load_config(config)
        self.enabled = bool(self.cfg.get("enabled", False))
        self.endpoint_url = str(self.cfg.get("endpoint_url", "")).strip()
        self.backup_interval_s = float(self.cfg.get("backup_interval_s", 3600.0))
        self.include_databases = bool(self.cfg.get("include_databases", True))
        self.include_images = bool(self.cfg.get("include_images", False))
        
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._last_backup_ts: float = 0.0

    def _load_config(self, user_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        defaults = {
            "enabled": False,
            "endpoint_url": "",
            "backup_interval_s": 3600,
            "include_databases": True,
            "include_images": False,
        }
        if _CONFIG_PATH.exists():
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    if isinstance(data.get("cloud_backup"), dict):
                        defaults.update(data["cloud_backup"])
            except Exception as e:
                logger.warning(f"Failed to read cloud_backup.yml: {e}")
        if isinstance(user_cfg, dict):
            defaults.update(user_cfg)
        return defaults

    def start(self) -> None:
        if not self.enabled:
            logger.info("Cloud backup is disabled by default. Skipping background thread.")
            return
        if not self.endpoint_url:
            logger.warning("Cloud backup enabled but no endpoint_url specified. Skipping.")
            return

        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run_loop, daemon=True, name="cloud_backup_sync")
        self._worker.start()
        logger.info(f"Cloud backup sync service started (interval: {self.backup_interval_s}s)")

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)

    def trigger_backup_now(self) -> Dict[str, Any]:
        """Manually trigger a cloud backup snapshot."""
        if not self.enabled or not self.endpoint_url:
            return {"ok": False, "reason": "backup_disabled_or_no_endpoint"}
        
        try:
            logger.info("Performing cloud backup snapshot...")
            with tempfile.TemporaryDirectory() as tmp_dir:
                zip_path = Path(tmp_dir) / "sentrybot_backup.zip"
                # Locate database files
                db_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
                if not db_dir.exists():
                    db_dir.mkdir(parents=True, exist_ok=True)
                
                shutil.make_archive(str(zip_path.with_suffix("")), "zip", db_dir)
                
                headers = {}
                token = self.cfg.get("auth_token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"

                with open(zip_path, "rb") as f:
                    resp = requests.post(
                        self.endpoint_url,
                        files={"backup_file": f},
                        headers=headers,
                        timeout=30.0,
                    )
                
                if resp.status_code == 200:
                    self._last_backup_ts = time.time()
                    logger.info("Cloud backup upload successful.")
                    return {"ok": True, "timestamp": self._last_backup_ts}
                else:
                    logger.warning(f"Cloud backup server returned status {resp.status_code}")
                    return {"ok": False, "status_code": resp.status_code}
        except Exception as e:
            logger.error(f"Cloud backup failed: {e}")
            return {"ok": False, "error": str(e)}

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            if now - self._last_backup_ts >= self.backup_interval_s:
                self.trigger_backup_now()
            self._stop_event.wait(timeout=10.0)
