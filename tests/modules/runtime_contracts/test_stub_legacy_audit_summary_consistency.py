from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_stub_legacy_audit_replacement_candidates_are_true_runtime_candidates():
    env = os.environ.copy()
    env["SENTRYBOT_DISABLE_AUTOSTART"] = "true"
    env["SENTRYBOT_RUNTIME_TARGET"] = "pi"
    env["SENTRYBOT_PI_RUNTIME_AUDIT"] = "1"
    proc = subprocess.run(
        [sys.executable, "tools/pi_runtime_stub_legacy_caller_audit.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads((ROOT / "pi_runtime_stub_legacy_caller_audit.json").read_text(encoding="utf-8"))
    candidates = data["replacement_candidates"]
    assert data["summary"]["runtime_replacement_candidate_files"] == len(candidates)
    for rec in candidates:
        assert rec["severities"].get("runtime_replacement_candidate", 0) > 0
    for rec in data["compatibility_reviews"]:
        if rec["path"] == "modules/oled_faces/services/legacy_map.py":
            assert rec["severities"].get("compatibility_review", 0) > 0
