"""Verification tests for Iteration 21: apps/, scripts/, and tools/ fixes and features."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_script_and_tool_roots_are_cwd_independent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    import scripts.assets.sync_pip_eyes_catalog as spec
    import scripts.install_all_requirements as iar
    import scripts.migrations.social_db_migrate as sdm
    import tools._audit_common as ac

    assert sdm._ROOT == ROOT
    assert spec.ROOT == ROOT
    assert ac.repo_root() == ROOT
    # Relative --venv-path resolves under repo_root when explicit, or cwd-independent via script logic
    args = iar.parse_args(["--profile", "pi", "--venv-path", ".venv", "--dry-run"])
    assert args.profile == "pi"
    out_md, out_json = ac.resolve_output_paths(ROOT, None, "X.md", "x.json")
    assert out_md == ROOT / "reports" / "X.md"
    assert out_json == ROOT / "reports" / "x.json"


def test_install_all_requirements_profile_filtering():
    import scripts.install_all_requirements as iar

    files = [
        ROOT / "requirements.txt",
        ROOT / "modules/vlm_bridge/requirements.txt",
        ROOT / "modules/voice/speak/requirements.txt",
        ROOT / "services/remote_multimodal_server/requirements.txt",
        ROOT / "services/remote_tts_server/requirements.txt",
    ]
    pi_labels = [iar.label_for(f, ROOT) for f in iar.filter_requirements_for_profile(files, "pi", ROOT)]
    ci_labels = [iar.label_for(f, ROOT) for f in iar.filter_requirements_for_profile(files, "ci", ROOT)]
    all_labels = [iar.label_for(f, ROOT) for f in iar.filter_requirements_for_profile(files, "all", ROOT)]

    assert "remote_tts_server" not in pi_labels
    assert "remote_multimodal_server" not in pi_labels
    assert "remote_tts_server" not in ci_labels
    assert "remote_multimodal_server" not in ci_labels
    assert "remote_tts_server" in all_labels
    assert "remote_multimodal_server" in all_labels


def test_install_piper_models_atomic_and_sha256(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import requests
    import scripts.setup.install_piper_models as ipm

    payload = b'{"audio": {"sample_rate": 22050}}'
    digest = hashlib.sha256(payload).hexdigest()
    dest = tmp_path / "model.onnx.json"

    class _FakeRequestsResp:
        def __init__(self, data: bytes):
            self._data = data
            self.headers = {"content-length": str(len(data))}

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 1024):
            yield self._data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(requests, "get", lambda *a, **kw: _FakeRequestsResp(payload))
    ipm._download("https://example.invalid/model.onnx.json", dest, insecure=False, expected_sha256=digest)

    assert dest.is_file()
    assert not list(tmp_path.glob("*.tmp"))
    assert ipm.compute_sha256(dest) == digest
    assert ipm.verify_sha256(dest, digest) is True
    assert dest.with_name(f"{dest.name}.sha256").read_text(encoding="utf-8").startswith(digest)

    bad_dest = tmp_path / "bad.onnx.json"
    with pytest.raises(ValueError, match="SHA256"):
        ipm._download("https://example.invalid/model.onnx.json", bad_dest, insecure=False, expected_sha256="0" * 64)
    assert not bad_dest.exists()
    assert not list(tmp_path.glob("*.tmp"))

    # Corrupt JSON caught atomically on .tmp before replace()
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _FakeRequestsResp(b"{not-valid-json"))
    with pytest.raises(json.JSONDecodeError):
        ipm._download("https://example.invalid/bad.onnx.json", bad_dest, insecure=False)
    assert not bad_dest.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_social_db_migrate_merge_chat_episodes_idempotent(tmp_path: Path):
    import scripts.migrations.social_db_migrate as sdm

    db = sdm.SocialDB(tmp_path / "social.sqlite3")
    try:
        pid = sdm._ensure_person(db, "Ada")
        db.chat_episodes.append(person_id=pid, role="user", text="Merhaba", ts=1000.0)
        entries = [
            {"role": "user", "text": "Merhaba", "ts": 1000.0},
            {"role": "assistant", "text": "Selam!", "ts": 1001.0},
        ]
        added_first = sdm._merge_chat_episodes(db, pid, entries)
        added_second = sdm._merge_chat_episodes(db, pid, entries)
        assert added_first == 1
        assert added_second == 0
        history = db.chat_episodes.recent_for_person(pid, limit=50)
        assert len(history) == 2
    finally:
        db.close()


def test_camera_capture_helper_gateway_and_cleanup(monkeypatch: pytest.MonkeyPatch):
    import numpy as np
    import scripts._camera_capture_helper as cch

    assert cch.resolve_gateway_snap_url().endswith(":8080/camera/snap")

    events: list[str] = []

    class _FakePublisher:
        def get_jpeg(self) -> bytes:
            return b"fakejpeg"

    class _FakeCapture:
        def __init__(self, cfg, publisher):
            self.cfg = cfg
            self.publisher = publisher

        def start(self) -> bool:
            events.append("cap_start")
            return True

        def stop(self) -> None:
            events.append("cap_stop")

    fake_capture_mod = types.ModuleType("modules.camera.services.capture")
    fake_capture_mod.CameraCapture = _FakeCapture
    fake_capture_mod.CaptureConfig = lambda **kw: kw
    fake_capture_mod.FramePublisher = _FakePublisher

    monkeypatch.setattr(cch, "fetch_frame_from_gateway", lambda *a, **kw: None)
    monkeypatch.setitem(sys.modules, "modules.camera.services.capture", fake_capture_mod)

    fake_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    with patch("cv2.imdecode", return_value=fake_frame):
        def _boom_selector(_candidate):
            raise RuntimeError("selector boom")

        # Exception inside loop still guarantees cap.stop(), falling through safely
        with patch("cv2.VideoCapture") as mock_vc:
            mock_cap = mock_vc.return_value
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, fake_frame)
            frame = cch.capture_live_face_frame(
                camera_num=0,
                max_attempts=3,
                poll_interval_s=0.0,
                frame_selector=_boom_selector,
                prefer_gateway=True,
            )
            assert frame is fake_frame
            assert events == ["cap_start", "cap_stop"]
            mock_cap.release.assert_called_once()


def test_run_robot_shutdown_idempotent_and_tui_shared():
    import apps.run_robot_tui as rtui
    import apps.sentrybot_tui as stui
    import scripts.run_robot as rr

    assert rtui.launch_tui is stui.launch_tui

    stopped: list[str] = []

    class _Svc:
        async def stop(self) -> None:
            stopped.append("svc")

    fake_app = types.SimpleNamespace(state=types.SimpleNamespace(started={"camera": _Svc()}))
    rr._STOPPED_SERVICE_IDS.clear()
    rr._stop_started_services(fake_app)
    rr._stop_started_services(fake_app)
    assert stopped == ["svc"]


def test_robot_arm_control_state_path_and_nonzero_on_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import tools.robot_arm_control as rac

    assert rac.STATE_PATH == ROOT / ".sentrybot_state" / "arm_state.json"

    policy_file = tmp_path / "policy.json"
    policy_file.write_text(
        json.dumps({"confirm_phrase": "CONFIRM ARM", "max_ttl_s": 60, "default_ttl_s": 30}),
        encoding="utf-8",
    )
    state_file = tmp_path / "state" / "arm_state.json"
    monkeypatch.setattr(rac, "POLICY_PATH", policy_file)
    monkeypatch.setattr(rac, "STATE_PATH", state_file)
    monkeypatch.delenv("SENTRYBOT_ALLOW_ARM", raising=False)

    ns = types.SimpleNamespace(profile="robot_safe_preview", confirm="", ttl_s=None, dry_run=False)
    rc = rac.cmd_arm(ns)
    assert rc == 2
    assert not state_file.exists()

    rc_disarm = rac.cmd_disarm(types.SimpleNamespace(reason="unit_test"))
    assert rc_disarm == 0
    assert state_file.is_file()
    assert not state_file.with_name(f"{state_file.name}.tmp").exists()
    assert json.loads(state_file.read_text(encoding="utf-8"))["armed"] is False


def test_pi_v4l2_reversible_camera_probe_releases_handle():
    import tools.pi_v4l2_reversible_camera_probe as probe

    class _FakeCap:
        def __init__(self, dev, backend):
            self.released = False

        def isOpened(self) -> bool:
            return True

        def release(self) -> None:
            self.released = True

    caps: list[_FakeCap] = []

    def _factory(dev, backend):
        cap = _FakeCap(dev, backend)
        caps.append(cap)
        return cap

    fake_cv2 = types.SimpleNamespace(CAP_V4L2=200, VideoCapture=_factory)
    dec = probe.probe_device("/dev/video0", allow_camera_open=True, cv2_module=fake_cv2)
    assert dec.camera_open_attempted is True
    assert dec.camera_opened is True
    assert dec.released is True
    assert dec.frame_captured is False
    assert caps and caps[0].released is True


def test_robot_capability_probe_and_gap_report_truthfulness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import tools.robot_capability_probe as rcp
    import tools.robot_hardware_gap_report as rhgr

    fake_root = tmp_path
    (fake_root / "config").mkdir(parents=True)
    (fake_root / "config" / "robot_execution_profiles.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rcp, "ROOT", fake_root)
    assert rcp.has_robot_safe_manual_profile() is False

    ep_map = {name: path for name, path, *_ in rhgr.ENDPOINTS}
    assert ep_map["tts"] == "/speak/status"
    assert ep_map["arduino"] == "/arduino/healthz"

    monkeypatch.setattr(rhgr, "fetch", lambda p: (True, {"ready": True, "tts": {"available": True}}, "ok"))
    assert rhgr.classify_endpoint("tts", "/speak/status", True, "robot_hardware")[0] == "READY"

    monkeypatch.setattr(rhgr, "fetch", lambda p: (True, {"ok": True, "firmware": "2.0"}, "ok"))
    assert rhgr.classify_endpoint("arduino", "/arduino/healthz", True, "robot_hardware")[0] == "READY"


def test_audit_tools_use_output_dir_and_no_shell_true(tmp_path: Path):
    import tools.pc_host_robot_target_code_readiness as cr
    import tools.robot_runtime_gateway_status_probe as rgp

    rc = cr.main(["--output-dir", str(tmp_path)])
    assert rc == 0
    report = json.loads((tmp_path / "pc_host_robot_target_code_readiness.json").read_text(encoding="utf-8"))
    assert report["overall_ok"] is True

    rgp_src = (ROOT / "tools" / "robot_runtime_gateway_status_probe.py").read_text(encoding="utf-8")
    assert "shell=True" not in rgp_src
    assert rgp.ROOT == ROOT
    assert "/arduino/healthz" in rgp.SAFE_GET_ENDPOINTS


def test_companion_e2e_and_imx500_lock_and_static_contracts(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    import tools.companion_e2e_robot_test as cert
    import tools.pi_camera_imx500_live_test as imx

    called_paths: list[str] = []

    def _fake_call(method, base, path, payload=None, timeout=15.0):
        called_paths.append(path)
        if path == "/autonomy/scenario/e2e":
            return {"path": path, "status": 500, "ok": False, "body": {}}
        return {"path": path, "status": 200, "ok": True, "body": {}}

    monkeypatch.setattr(cert, "call", _fake_call)
    monkeypatch.setattr(sys, "argv", ["companion_e2e_robot_test.py"])
    rc = cert.main()
    assert "/autonomy/scenario/e2e" in called_paths
    # Failed POST step MUST cause exit code 2 even if GET steps[:6] succeeded
    assert rc == 2
    capsys.readouterr()

    class _GatewayResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    monkeypatch.setattr(
        imx.urllib.request,
        "urlopen",
        lambda req, timeout=1.5: _GatewayResp(json.dumps({"capture": {"running": True}}).encode("utf-8")),
    )
    lock = imx.check_gateway_camera_lock("http://127.0.0.1:8080")
    assert lock["capture_running"] is True

    # Static checks for bash & script hygiene fixes
    install_sh = (ROOT / "scripts" / "install_all.sh").read_text(encoding="utf-8")
    assert "libqtgui4" not in install_sh and "libqtwebkit4" not in install_sh
    assert "httpx" in install_sh and "textual" in install_sh
    systemd_sh = (ROOT / "tools" / "pi_systemd_install.sh").read_text(encoding="utf-8")
    assert "SENTRYBOT_SERVICE_USER" in systemd_sh and "User=" in systemd_sh
    dep_sh = (ROOT / "tools" / "pi_dependency_installer.sh").read_text(encoding="utf-8")
    assert "modules/voice/speak/requirements.txt" in dep_sh
    assert "modules/speak/requirements.txt" not in dep_sh
    dl_sh = (ROOT / "tools" / "pi_model_downloader_layout.sh").read_text(encoding="utf-8")
    assert 'if [[ "$DOWNLOAD_EN" == "1" ]]' in dl_sh


def test_pi_hardware_preflight_doctor_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import tools.pi_hardware_preflight as preflight

    (tmp_path / ".sentrybot_state").mkdir(parents=True)
    (tmp_path / ".sentrybot_state" / "arm_state.json").write_text(
        json.dumps({"armed": True, "hardware_enabled": False, "profile": "robot_safe_manual"}),
        encoding="utf-8",
    )
    (tmp_path / "deploy" / "systemd").mkdir(parents=True)
    (tmp_path / "deploy" / "systemd" / "sentrybot.service").write_text(
        "[Service]\nUser=definitely_wrong_user_xyz\nGroup=pi\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        preflight.PiHardwareRuntime,
        "status",
        lambda self: {"ok": True, "is_raspberry_pi": True, "video_devices": [], "reason": "ok"},
    )
    monkeypatch.setattr(preflight, "collect_asset_truth", lambda root: {"ok": True, "required_missing": []})

    import tools.pi_camera_imx500_live_test as imx
    import tools.pi_cv2_package_backend_verification as cv2v
    import tools.pi_runtime_readiness as rr_mod
    import tools.pi_v4l2_reversible_camera_probe as v4l2p

    monkeypatch.setattr(rr_mod, "collect", lambda: {"ok": True, "missing": []})
    monkeypatch.setattr(cv2v, "collect_installed_opencv_packages", lambda: {"opencv-python": "4.10.0"})
    monkeypatch.setattr(cv2v, "collect_cv2_runtime_info", lambda: {"cv2_importable": True, "cv2_version": "4.10.0"})
    monkeypatch.setattr(cv2v, "analyze_cv2_environment", lambda **kw: {"overall_ok": True})
    monkeypatch.setattr(v4l2p, "build_report", lambda **kw: {"overall_ok": True, "probe": {"camera_open_attempted": kw.get("allow_camera_open", False)}})
    monkeypatch.setattr(imx, "check_gateway_camera_lock", lambda url: {"reachable": False, "capture_running": False})

    report = preflight.collect_doctor_report(tmp_path)
    assert report["ok"] is True
    assert report["doctor"] is True
    assert report["camera_probe"]["probe"]["camera_open_attempted"] is False
    assert report["summary"]["checks"]["arm_safe_disarmed"] is False
    assert report["summary"]["checks"]["systemd_user_aligned"] is False
    assert "robot_arm_currently_armed" in report["summary"]["warnings"]
    assert "systemd_service_user_mismatch" in report["summary"]["warnings"]
