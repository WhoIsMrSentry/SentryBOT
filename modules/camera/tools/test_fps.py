import cv2
import time

def main() -> None:
    # Set your stream URL (default Raspberry Pi host)
    url = "http://pi.local:8000/video"
    cap = cv2.VideoCapture(url)

    frame_count = 0
    start_time = time.time()

    cv2.namedWindow("Stream", cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to read from stream. Retrying...")
            time.sleep(0.5)
            continue

        frame_count += 1
        elapsed = time.time() - start_time
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            height, width = frame.shape[:2]
            print(f"FPS: {fps:.2f} | Resolution: {width}x{height}")
            frame_count = 0
            start_time = time.time()

        cv2.imshow("Stream", frame)
        if cv2.waitKey(1) == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
