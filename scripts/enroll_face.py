#!/usr/bin/env python3
"""SentryBOT Face Enrollment & Person Identity CLI tool.

Allows enrolling new faces directly from the camera or from an image file,
associating them with relationships (owner, family, friend, known) and recognition levels (1-5).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="SentryBOT Face & Person Enrollment Tool")
    parser.add_argument("--name", required=True, help="Person's name (e.g. Emir, Alice)")
    parser.add_argument(
        "--relationship",
        choices=["owner", "family", "friend", "known", "stranger"],
        default="known",
        help="Relationship category (default: known)",
    )
    parser.add_argument(
        "--level",
        type=int,
        choices=[0, 1, 2, 3, 4, 5],
        default=None,
        help="Recognition level 0-5 (default: 5 for owner, 3 for friend, 2 for known)",
    )
    parser.add_argument("--image", help="Path to an image file containing the person's face")
    parser.add_argument("--camera", type=int, default=0, help="Camera index if capturing live (default: 0)")
    args = parser.parse_args()

    try:
        import cv2
    except ImportError:
        print("[ERROR] OpenCV (cv2) is not installed in the current environment.", file=sys.stderr)
        return 1

    name = args.name.strip()
    relationship = args.relationship
    if args.level is None:
        default_levels = {"owner": 5, "family": 4, "friend": 3, "known": 2, "stranger": 0}
        level = default_levels.get(relationship, 2)
    else:
        level = args.level

    # Load image
    frame = None
    if args.image:
        img_path = Path(args.image)
        if not img_path.exists():
            print(f"[ERROR] Image path does not exist: {img_path}", file=sys.stderr)
            return 2
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"[ERROR] Could not read image: {img_path}", file=sys.stderr)
            return 2
        print(f"[INFO] Loaded image from {img_path}")
    else:
        print("[INFO] Capturing frame from camera...")
        import numpy as np

        # 1. Try to fetch frame from active Gateway if robot is already running
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:8000/camera/frame")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    raw_bytes = resp.read()
                    frame = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        print("[INFO] Captured live frame from running SentryBOT Gateway.")
        except Exception:
            pass

        # 2. Standalone camera capture via Picamera2 Subprocess Bridge
        if frame is None:
            try:
                from modules.camera.services.capture import CameraCapture, CaptureConfig, FramePublisher
                cfg = CaptureConfig(camera_num=args.camera, size=(1280, 720), frame_rate=15)
                pub = FramePublisher()
                cap = CameraCapture(cfg=cfg, publisher=pub)
                if cap.start():
                    print("[INFO] Camera hardware initialized. Waiting for auto-exposure...")
                    time.sleep(2.0)
                    for _ in range(30):
                        jpeg_bytes = pub.get_jpeg()
                        if jpeg_bytes:
                            frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                break
                        time.sleep(0.1)
                    cap.stop()
            except Exception as exc:
                print(f"[WARN] CameraCapture bridge fallback: {exc}")

        # 3. Fallback to standard OpenCV VideoCapture
        if frame is None:
            try:
                vcap = cv2.VideoCapture(args.camera)
                if vcap.isOpened():
                    for _ in range(5):  # warm up auto-exposure
                        vcap.read()
                    ret, frame = vcap.read()
                    vcap.release()
            except Exception as exc:
                print(f"[WARN] OpenCV VideoCapture fallback: {exc}")

    if frame is None:
        print("[ERROR] Failed to capture a frame from the camera. Please check camera connection or supply --image.", file=sys.stderr)
        return 3

    # Initialize FaceManager and PersonIdentity
    from modules.vlm_bridge.services.face_manager import FaceManager
    from modules.vlm_bridge.services.person_identity import PersonIdentity

    face_mgr = FaceManager()
    success = face_mgr.register_face(name, frame)

    if not success:
        print(f"[ERROR] No face detected in frame or descriptor extraction failed for '{name}'. Ensure face is well-lit and facing the camera.", file=sys.stderr)
        return 4

    person_id = PersonIdentity()
    record = person_id.remember_person(name, relationship=relationship, recognition_level=level)

    print(f"\n\033[1;32m[SUCCESS] Person enrolled successfully!\033[0m")
    print(f"  Name:               {name}")
    print(f"  Relationship:       {record.relationship}")
    print(f"  Recognition Level:  {record.recognition_level} / 5")
    print(f"  Person ID:          {record.person_id}")
    print(f"  Total Known Faces:  {len(face_mgr.known_face_names)}")
    print(f"  Known Face List:    {', '.join(face_mgr.known_face_names)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
