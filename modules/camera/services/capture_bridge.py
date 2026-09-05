from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

BRIDGE_WORKER_CODE = """
import sys
import struct
import time

def main():
    camera_num = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 720
    fps = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    quality = int(sys.argv[5]) if len(sys.argv) > 5 else 80
    flip = sys.argv[6].strip().lower() if len(sys.argv) > 6 else 'none'
    pixel_format = sys.argv[7] if len(sys.argv) > 7 else 'RGB888'

    try:
        from picamera2 import Picamera2
        import cv2
    except Exception as exc:
        sys.stderr.write(f"IMPORT_ERROR: {exc}\\n")
        sys.stderr.flush()
        sys.exit(1)

    try:
        picam = Picamera2(camera_num)
        config = picam.create_video_configuration(
            main={"size": (width, height), "format": pixel_format},
            controls={"FrameRate": float(max(1, fps))},
            buffer_count=4,
            queue=True,
        )
        picam.configure(config)
        picam.start()
    except Exception as exc:
        sys.stderr.write(f"CONFIG_ERROR: {exc}\\n")
        sys.stderr.flush()
        sys.exit(2)

    sys.stderr.write("READY\\n")
    sys.stderr.flush()

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(max(1, min(100, quality)))]

    try:
        while True:
            req = picam.capture_request()
            try:
                frame = req.make_array("main")
                if pixel_format.upper().startswith("RGB"):
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                if flip in ("h", "horizontal"):
                    frame = cv2.flip(frame, 1)
                elif flip in ("v", "vertical"):
                    frame = cv2.flip(frame, 0)
                elif flip in ("hv", "both", "180", "rotate180", "r180"):
                    frame = cv2.flip(frame, -1)
                elif flip in ("90", "rotate90", "r90"):
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif flip in ("270", "rotate270", "r270"):
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if ok:
                    b = encoded.tobytes()
                    sys.stdout.buffer.write(struct.pack(">I", len(b)) + b)
                    sys.stdout.buffer.flush()
            finally:
                req.release()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    except Exception as exc:
        sys.stderr.write(f"LOOP_ERROR: {exc}\\n")
        sys.stderr.flush()
    finally:
        try:
            picam.stop()
            picam.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
"""


def find_system_picam_python() -> Optional[str]:
    """Locate a system Python binary (e.g. /usr/bin/python3) that has picamera2 available."""
    candidates = ["/usr/bin/python3", "/usr/bin/python3.13", "/usr/bin/python3.12"]
    for cand in candidates:
        if os.path.isfile(cand) and cand != sys.executable:
            try:
                res = subprocess.run(
                    [cand, "-c", "import picamera2; print('OK')"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0 and "OK" in res.stdout:
                    return cand
            except Exception:
                pass
    return None
