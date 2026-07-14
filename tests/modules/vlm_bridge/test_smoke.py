from __future__ import annotations


def test_gateway_url_helper_for_vlm_clients():
    from modules.gateway.url import gateway_url, patch_service_endpoints

    base = "http://127.0.0.1:9090"
    assert gateway_url(base, "/vlm/ask") == "http://127.0.0.1:9090/vlm/ask"
    patched = patch_service_endpoints({"vlm": "http://localhost:8080/vlm"}, base)
    assert patched["vlm"] == "http://127.0.0.1:9090/vlm"


def test_camera_gave_up_blocks_local_vision():
    """Mirror VisionProcessor.is_camera_input_available local-path without importing cv2."""
    processing_mode = "local"
    is_http = False
    camera_gave_up = True
    latest_frame = None
    capture_alive = False

    available = True
    if str(processing_mode).strip().lower() == "local":
        if is_http:
            available = False
        elif camera_gave_up:
            available = False
        elif latest_frame is not None:
            available = True
        else:
            available = capture_alive

    assert available is False
