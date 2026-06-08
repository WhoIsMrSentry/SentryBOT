"""
Production-ready Async Sensor Feedback Loop.
Polls real hardware sensors via ServiceClient HTTP calls.
Runs in a daemon thread to never block the main agent or autonomy loop.
"""
import threading
import time
import logging
from typing import Optional

logger = logging.getLogger("agent.sensors")


class SensorFeedbackLoop:
    """
    Background thread that periodically reads real sensor data via ServiceClient
    and pushes updates into the WorldState for LLM context injection.
    """

    def __init__(self, world_state, client=None, poll_hz: float = 5.0):
        """
        Args:
            world_state: The shared WorldState instance.
            client: ServiceClient from AutonomyBrain (for real sensor reads).
            poll_hz: Polling frequency in Hz (default 5 = every 200ms).
        """
        self.world_state = world_state
        self.client = client
        self.poll_interval = 1.0 / max(0.1, poll_hz)
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info("Sensor feedback loop started (interval=%.2fs).", self.poll_interval)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Sensor feedback loop stopped.")

    def _poll_loop(self):
        """
        Background loop reading real sensors through ServiceClient.
        Updates WorldState atomically so the agent always sees consistent data.
        """
        while self.running:
            updates = {}
            try:
                if self.client:
                    # ── Ultrasonic distance ──
                    ultra = self.client.read_sensor("ultra_read")
                    if ultra and isinstance(ultra, dict):
                        dist = ultra.get("cm", ultra.get("distance", -1))
                        updates["distance_front_cm"] = float(dist) if dist is not None else -1

                    # ── IMU (Inertial Measurement Unit) ──
                    imu = self.client.read_sensor("imu_read")
                    if imu and isinstance(imu, dict):
                        updates["imu_pitch"] = float(imu.get("pitch", 0))
                        updates["imu_roll"] = float(imu.get("roll", 0))

                    # ── RFID Last ──
                    rfid = self.client.read_sensor("rfid_last")
                    if rfid and isinstance(rfid, dict):
                        uid = rfid.get("uid")
                        if uid:
                            updates["last_rfid"] = str(uid)

                    # ── Vision (person detection) ──
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

                    # ── Continuous environment perception (VLM scene cache) ──
                    try:
                        ctx = self.client.get_visual_context()
                        if isinstance(ctx, dict) and ctx.get("available") and ctx.get("context"):
                            self.world_state.update_scene(ctx)
                    except Exception:
                        pass

                # Apply all updates atomically
                if updates:
                    self.world_state.update_state(updates)

            except Exception as e:
                logger.error("Sensor poll error: %s", e)

            time.sleep(self.poll_interval)
