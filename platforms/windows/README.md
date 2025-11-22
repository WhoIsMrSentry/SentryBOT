# Windows platform overrides

This provides Windows-friendly implementations and configs to run and test on a PC:
- Camera uses OpenCV (DirectShow) instead of PiCamera2
- Default webcam index 0; MJPG; low buffer for lower latency
- You can adjust overrides via environment variables: CAM_SOURCE, CAM_WIDTH, CAM_HEIGHT, etc.
