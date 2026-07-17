"""
Budgeted background sensor loop for Agent Core.

The old loop read Arduino sensors and VLM cache every tick. At 5 Hz this created
thousands of /arduino/request and /vlm/context/latest entries during PC tests.
This version separates loop tick rate from per-channel polling budgets.
"""
from __future__ import annotations

# --- SentryBOT perception/vision boundary contract ---
PERCEPTION_VISION_COMPATIBILITY = True
PERCEPTION_VISION_BOUNDARY_ROLE = 'agent_core_compat_sensor_loop'
PERCEPTION_VISION_RUNTIME_OWNER = 'raw perception: modules.camera/modules.vlm_bridge; semantic perception: modules.autonomy'
PERCEPTION_VISION_BOUNDARY_REASON = 'SensorFeedbackLoop is still constructed by AgentOrchestrator and updates agent_core WorldState from VLM/camera context. Keep as compatibility helper until AgentOrchestrator dependency is separated.'
# --- End SentryBOT perception/vision boundary contract ---

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger("agent.sensors")


def _safe_float(value, fallback: float, minimum: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        out = float(fallback)
    if out < minimum:
        return float(fallback)
    return out


def _pc_test_mode() -> bool:
    value = os.environ.get("SENTRYBOT_PC_TEST") or os.environ.get("SENTRYBOT_PROFILE") or ""
    return str(value).strip().lower() in {"1", "true", "yes", "pc", "pc-test", "test"}


class SensorFeedbackLoop:
    """Poll hardware and vision cache with independent budgets."""

    def __init__(
        self,
        world_state,
        client=None,
        poll_hz: float = 2.0,
        enabled: bool = True,
        hardware_interval_s: float = 2.0,
        vision_results_interval_s: float = 5.0,
        visual_context_interval_s: float = 10.0,
        skip_hardware_on_pc: bool = True,
    ):
        self.world_state = world_state
        self.client = client
        self.enabled = bool(enabled)
        self.loop_interval = 1.0 / max(0.1, _safe_float(poll_hz, 2.0, 0.1))
        self.hardware_interval_s = _safe_float(hardware_interval_s, 2.0, 0.2)
        self.vision_results_interval_s = _safe_float(vision_results_interval_s, 5.0, 0.5)
        self.visual_context_interval_s = _safe_float(visual_context_interval_s, 10.0, 1.0)
        self.skip_hardware_on_pc = bool(skip_hardware_on_pc)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._last: dict[str, float] = {}

    @property
    def pc_test(self) -> bool:
        return _pc_test_mode()

    def start(self):
        if not self.enabled:
            logger.info("Sensor feedback loop disabled by config.")
            return
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info(
            "Sensor feedback loop started (tick=%.2fs hardware=%.1fs vision_results=%.1fs context=%.1fs pc_test=%s).",
            self.loop_interval,
            self.hardware_interval_s,
            self.vision_results_interval_s,
            self.visual_context_interval_s,
            self.pc_test,
        )

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Sensor feedback loop stopped.")

    def _due(self, key: str, interval_s: float, now: float) -> bool:
        last = float(self._last.get(key, 0.0) or 0.0)
        if now - last < interval_s:
            return False
        self._last[key] = now
        return True

    def _read_hardware(self) -> dict:
        updates = {}
        if self.pc_test and self.skip_hardware_on_pc:
            return updates

        ultra = self.client.read_sensor("ultra_read")
        if ultra and isinstance(ultra, dict):
            dist = ultra.get("cm", ultra.get("distance", -1))
            updates["distance_front_cm"] = float(dist) if dist is not None else -1

        imu = self.client.read_sensor("imu_read")
        if imu and isinstance(imu, dict):
            updates["imu_pitch"] = float(imu.get("pitch", 0))
            updates["imu_roll"] = float(imu.get("roll", 0))

        rfid = self.client.read_sensor("rfid_last")
        if rfid and isinstance(rfid, dict):
            uid = rfid.get("uid")
            if uid:
                updates["last_rfid"] = str(uid)
        return updates

    def _read_vision_results(self) -> dict:
        updates = {}
        try:
            vision = self.client.get_latest_vision_results(limit=1)
            if vision and isinstance(vision, list) and len(vision) > 0:
                latest = vision[0]
                updates["person_detected"] = bool(latest.get("name") or latest.get("label"))
                updates["person_name"] = str(latest.get("name", "")) if latest.get("name") else None
            else:
                updates["person_detected"] = False
        except Exception:
            pass
        return updates

    def _read_visual_context(self) -> None:
        try:
            ctx = self.client.get_visual_context()
            if isinstance(ctx, dict) and ctx.get("available") and ctx.get("context"):
                self.world_state.update_scene(ctx)
        except Exception:
            pass

    def _poll_loop(self):
        while self.running:
            now = time.time()
            updates = {}
            try:
                if self.client:
                    if self._due("hardware", self.hardware_interval_s, now):
                        updates.update(self._read_hardware())
                    if self._due("vision_results", self.vision_results_interval_s, now):
                        updates.update(self._read_vision_results())
                    if self._due("visual_context", self.visual_context_interval_s, now):
                        self._read_visual_context()

                if updates:
                    self.world_state.update_state(updates)
            except Exception as exc:
                logger.error("Sensor poll error: %s", exc)

            time.sleep(self.loop_interval)