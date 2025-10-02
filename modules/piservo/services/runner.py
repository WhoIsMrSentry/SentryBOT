from __future__ import annotations
import time

try:
    from .driver import Servo, ServoConfig
    from .ears import EMOTION_POSES, gesture_sound, gesture_wakeword
except Exception:
    from driver import Servo, ServoConfig  # type: ignore
    from ears import EMOTION_POSES, gesture_sound, gesture_wakeword  # type: ignore


class EarRunner:
    def __init__(self, left_cfg: ServoConfig, right_cfg: ServoConfig):
        self.left = Servo(left_cfg)
        self.right = Servo(right_cfg)
        # Start at up position (90)
        self.set_angles(90, 90)

    def set_angles(self, left: float, right: float) -> None:
        self.left.set_angle(left)
        self.right.set_angle(right)

    def emotion(self, name: str) -> None:
        pose = EMOTION_POSES.get(name.lower(), EMOTION_POSES.get("neutral", None))
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
        # alias for gesture
        self.gesture(kind)
