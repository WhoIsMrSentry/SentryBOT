from __future__ import annotations

from modules.camera.services import capture


class FakeCv2:
    CAP_DSHOW = 700
    CAP_MSMF = 1400
    CAP_V4L2 = 200
    CAP_ANY = 0


def test_pi_linux_backend_order_prefers_v4l2_and_excludes_dshow():
    backends = capture._opencv_robot_backend_candidates(FakeCv2, os_name="posix")
    assert backends[0] == FakeCv2.CAP_V4L2
    assert FakeCv2.CAP_ANY in backends
    assert FakeCv2.CAP_DSHOW not in backends
    assert FakeCv2.CAP_MSMF not in backends


def test_windows_backend_kept_only_as_pc_dev_fallback():
    backends = capture._opencv_robot_backend_candidates(FakeCv2, os_name="nt")
    assert backends[0] == FakeCv2.CAP_DSHOW
    assert FakeCv2.CAP_ANY in backends


def test_backend_helper_accepts_missing_backend_constants():
    class MinimalCv2:
        CAP_ANY = 0

    assert capture._opencv_robot_backend_candidates(MinimalCv2, os_name="posix") == [None, 0, None]
