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
        try:
            # Check if CameraCapture bridge or Picamera2 is available
            from modules.camera.services.capture import CameraCapture
            cap = CameraCapture(source=args.camera, width=1280, height=720, fps=15)
            if cap.start():
                print("[INFO] Camera started. Stabilizing 2 seconds...")
                time.sleep(2.0)
                frame = cap.read_frame()
                cap.stop()
        except Exception as exc:
            print(f"[WARN] CameraCapture bridge fallback: {exc}")

        if frame is None:
            # Fallback to standard cv2.VideoCapture
            vcap = cv2.VideoCapture(args.camera)
            if vcap.isOpened():
                for _ in range(5):  # warm up auto-exposure
                    vcap.read()
                ret, frame = vcap.read()
                vcap.release()

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
