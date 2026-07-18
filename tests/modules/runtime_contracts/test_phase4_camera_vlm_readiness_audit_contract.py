from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_phase4_readiness_audit_is_status_only_and_safe():
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", "tools/pi_robot_runtime_refactor_audit.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report_path = ROOT / "phase4_camera_vlm_robot_readiness_audit.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["safety"]["camera_started"] is False
    assert data["safety"]["vlm_started"] is False
    assert data["safety"]["hardware_enabled"] is False
    assert data["phase"] == "phase4_camera_vlm_robot_activation_preparation"
    assert data["activation_allowed_now"] is False
    assert data["next_required_contracts"][0] == "camera_reversible_start_stop_contract"
