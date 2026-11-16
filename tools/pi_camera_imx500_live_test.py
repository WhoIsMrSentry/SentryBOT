from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def check_gateway_camera_lock(gateway_url: str, timeout_s: float = 1.5) -> dict:
    """Return status-only gateway lock info without starting camera hardware."""
    url = gateway_url.rstrip("/") + "/camera/status"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        capture = payload.get("capture") if isinstance(payload.get("capture"), dict) else {}
        running = bool(capture.get("running") or payload.get("running"))
        return {"reachable": True, "capture_running": running, "payload": payload}
    except Exception as exc:
        return {"reachable": False, "capture_running": False, "detail": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--gateway-url", default="http://127.0.0.1:8080")
    ap.add_argument("--ignore-gateway", action="store_true")
    args = ap.parse_args()
    if not Path(args.model).is_file():
        print(json.dumps({"ok": False, "error": "model_missing", "model": args.model}, indent=2))
        return 2
    if not args.ignore_gateway:
        lock = check_gateway_camera_lock(args.gateway_url)
        if lock.get("capture_running"):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "gateway_camera_active",
                        "detail": "Stop gateway camera capture before exclusive IMX500 test or pass --ignore-gateway.",
                        "gateway_url": args.gateway_url,
                    },
                    indent=2,
                )
            )
            return 2
    try:
        from picamera2 import Picamera2
        from picamera2.devices.imx500 import IMX500
    except Exception as e:
        print(json.dumps({"ok": False, "error": "picamera2_imx500_unavailable", "detail": str(e)}, indent=2))
        return 2
    imx500 = IMX500(args.model)
    picam2 = Picamera2(imx500.camera_num)
    cfg = picam2.create_preview_configuration(main={"format": "RGB888", "size": (args.width, args.height)}, buffer_count=6)
    picam2.configure(cfg)
    picam2.start()
    deadline = time.monotonic() + args.seconds
    frame_interval_s = (1.0 / args.fps) if args.fps > 0 else 0.0
    frames = 0
    outputs = 0
    last_shapes = None
    last_kpi = None
    try:
        while time.monotonic() < deadline:
            tick_start = time.monotonic()
            req = picam2.capture_request()
            meta = req.get_metadata()
            out = imx500.get_outputs(meta)
            if out is not None:
                outputs += 1
                try:
                    last_shapes = [list(x.shape) for x in out]
                except Exception:
                    last_shapes = str(type(out))
            try:
                last_kpi = imx500.get_kpi_info(meta)
            except Exception:
                pass
            req.release()
            frames += 1
            if frame_interval_s > 0:
                sleep_s = frame_interval_s - (time.monotonic() - tick_start)
                if sleep_s > 0:
                    time.sleep(sleep_s)
    finally:
        picam2.stop()
    result = {"ok": frames > 0, "frames": frames, "outputs": outputs, "last_output_shapes": last_shapes, "last_kpi": last_kpi, "model": args.model}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2
if __name__ == "__main__":
    raise SystemExit(main())
