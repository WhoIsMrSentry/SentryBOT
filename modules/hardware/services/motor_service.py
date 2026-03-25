"""
Production-ready HAL Motor Service.
Delegates to the existing ServiceClient HTTP layer for NEMA stepper control.
Returns feedback strings for the Agent's proprioception system.
"""
import logging
from typing import Optional

logger = logging.getLogger("hardware.motor")


class MotorService:
    """
    Controls NEMA stepper motors via ServiceClient -> Arduino serial.
    Returns action feedback strings for the AgentOrchestrator's proprioception loop.
    """

    def __init__(self, client):
        self.client = client

    def drive(self, stepper_id: int, mode: str, value: int, drive_param: int = 200) -> str:
        """
        Move a stepper motor.
        Args:
            stepper_id: 0 or 1
            mode: "pos" (position) or "vel" (velocity)
            value: target position (steps) or velocity (steps/s)
            drive_param: speed parameter for position mode
        Returns:
            "SUCCESS" or "ERROR_..." feedback string for proprioception.
        """
        try:
            result = self.client.set_stepper(stepper_id, mode, value, drive=drive_param)
            if result and isinstance(result, dict):
                if result.get("ok", False):
                    logger.info("Stepper[%d] %s=%d -> SUCCESS", stepper_id, mode, value)
                    return "SUCCESS"
                elif result.get("stall"):
                    logger.warning("Stepper[%d] STALL DETECTED", stepper_id)
                    return "ERROR_STALL_DETECTED"
                else:
                    error = result.get("error", "unknown")
                    logger.warning("Stepper[%d] error: %s", stepper_id, error)
                    return f"ERROR_{error}"
            logger.warning("Stepper[%d] no response from Arduino", stepper_id)
            return "ERROR_NO_RESPONSE"
        except Exception as e:
            logger.error("Stepper[%d] exception: %s", stepper_id, e)
            return f"ERROR_EXCEPTION_{e}"

    def drive_both(self, left_vel: int, right_vel: int) -> str:
        """Drive both wheels simultaneously (differential drive)."""
        r0 = self.drive(0, "vel", left_vel)
        r1 = self.drive(1, "vel", right_vel)
        if "ERROR" in r0 or "ERROR" in r1:
            return f"ERROR_PARTIAL: L={r0} R={r1}"
        return "SUCCESS"

    def stop(self) -> str:
        """Emergency stop all motors."""
        try:
            self.client.robot_command("estop")
            logger.info("Emergency STOP issued.")
            return "SUCCESS_ESTOP"
        except Exception as e:
            logger.error("Emergency stop failed: %s", e)
            return f"ERROR_ESTOP_{e}"

    def robot_command(self, cmd: str) -> Optional[dict]:
        """Send simple robot commands: stand, sit, home, zero_now."""
        try:
            return self.client.robot_command(cmd)
        except Exception as e:
            logger.error("Robot command '%s' failed: %s", cmd, e)
            return None
