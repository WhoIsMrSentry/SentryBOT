from __future__ import annotations

import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class RuntimeTarget:
    system: str
    machine: str
    model: str
    is_raspberry_pi: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _read_model() -> str:
    path = Path("/proc/device-tree/model")
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip("\x00\n ")
    except OSError:
        return ""


def detect_runtime_target() -> RuntimeTarget:
    system = platform.system().strip().lower()
    machine = platform.machine().strip().lower()
    model = _read_model()
    is_linux = system == "linux"
    is_arm64 = machine in {"aarch64", "arm64"}
    is_pi_model = "raspberry pi" in model.lower()
    ok = is_linux and is_arm64 and is_pi_model
    if ok:
        reason = "raspberry_pi_detected"
    elif not is_linux:
        reason = "linux_required"
    elif not is_arm64:
        reason = "arm64_required"
    else:
        reason = "raspberry_pi_model_not_detected"
    return RuntimeTarget(system, machine, model, ok, reason)


def assert_raspberry_pi() -> RuntimeTarget:
    target = detect_runtime_target()
    if not target.is_raspberry_pi:
        raise RuntimeError(
            "SentryBOT robot runtime only supports Raspberry Pi 5. "
            f"system={target.system!r} machine={target.machine!r} "
            f"model={target.model!r} reason={target.reason}"
        )
    return target


def status() -> Dict[str, Any]:
    target = detect_runtime_target()
    return {
        "ok": target.is_raspberry_pi,
        "target": "raspberry_pi_5" if target.is_raspberry_pi else "unsupported",
        **target.to_dict(),
    }


__all__ = ["RuntimeTarget", "detect_runtime_target", "assert_raspberry_pi", "status"]
