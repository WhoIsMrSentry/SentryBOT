from __future__ import annotations
import time

try:
    from .driver import Servo, ServoConfig
    from .ears import EMOTION_POSES, gesture_sound, gesture_wakeword, pose_for_emotion
    from .ear_reflex import EarReflexEngine
except Exception:
    from driver import Servo, ServoConfig  # type: ignore
    from ears import EMOTION_POSES, gesture_sound, gesture_wakeword, pose_for_emotion  # type: ignore
    from ear_reflex import EarReflexEngine  # type: ignore


class EarRunner:
    def __init__(self, left_cfg: ServoConfig, right_cfg: ServoConfig):
        self.left = Servo(left_cfg)
        self.right = Servo(right_cfg)
        self.ear_reflex = EarReflexEngine(neutral_left=90.0, neutral_right=90.0)
        # Start at up position (90)
        self.set_angles(90, 90)

    def set_angles(self, left: float, right: float) -> None:
        self.left.set_angle(left)
        self.right.set_angle(right)

    def reflex(self, angle: float, energy: float = 1.0) -> tuple[float, float]:
        angles = self.ear_reflex.compute_reflex(angle, energy)
        self.set_angles(angles.left, angles.right)
        return angles.left, angles.right

    def emotion(self, name: str) -> None:
        pose = pose_for_emotion(name)
        if not pose:
            return
        self.set_angles(pose.left, pose.right)

    def gesture(self, name: str) -> None:
        n = name.lower()
        if n == "wakeword":
            l, r = gesture_wakeword()
            self.set_angles(l, r)
            time.sleep(0.2)
            self.set_angles(90, 90)
        elif n == "sound":
            l, r = gesture_sound()
            self.set_angles(l, r)
            time.sleep(0.3)
            self.set_angles(90, 90)

    def event(self, kind: str) -> None:
        k = str(kind or "").lower()
        if k.startswith("doa:") or k.startswith("sound:"):
            try:
                angle = float(k.split(":", 1)[1])
                self.reflex(angle)
                return
            except (ValueError, IndexError):
                pass
        self.gesture(kind)
