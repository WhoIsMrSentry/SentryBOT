import argparse
import os
import time

import cv2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure MJPEG stream FPS and resolution.")
    parser.add_argument(
        "--url",
        default=os.getenv("CAMERA_STREAM_URL", "http://127.0.0.1:8000/video"),
        help="Camera MJPEG stream URL",
    )
    parser.add_argument("--max-retries", type=int, default=10, help="Max consecutive read failures before exiting")
    parser.add_argument(
        "--duration-s",
        type=float,
        default=0.0,
        help="Stop automatically after N seconds (0=until ESC)",
    )
    parser.add_argument("--headless", action="store_true", help="Do not open OpenCV preview window")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cap = cv2.VideoCapture(args.url)
    frame_count = 0
    failures = 0
    started = time.monotonic()
    fps_tick = started

    if not args.headless:
        cv2.namedWindow("Stream", cv2.WINDOW_NORMAL)

    try:
        while True:
            if args.duration_s > 0.0 and (time.monotonic() - started) >= args.duration_s:
                break
            ret, frame = cap.read()
            if not ret or frame is None:
                failures += 1
                print(f"Failed to read from stream ({failures}/{args.max_retries}). Retrying...")
                if failures >= max(1, args.max_retries):
                    return 1
                time.sleep(0.5)
                continue

            failures = 0
            frame_count += 1
            elapsed = time.monotonic() - fps_tick
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                height, width = frame.shape[:2]
                print(f"FPS: {fps:.2f} | Resolution: {width}x{height}")
                frame_count = 0
                fps_tick = time.monotonic()

            if not args.headless:
                cv2.imshow("Stream", frame)
                if cv2.waitKey(1) == 27:
                    break
    finally:
        cap.release()
        if not args.headless:
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
