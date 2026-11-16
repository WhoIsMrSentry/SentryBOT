from __future__ import annotations


def test_gateway_url_helper_for_vlm_clients():
    from modules.gateway.url import gateway_url, patch_service_endpoints

    base = "http://127.0.0.1:9090"
    assert gateway_url(base, "/vlm/ask") == "http://127.0.0.1:9090/vlm/ask"
    patched = patch_service_endpoints({"vlm": "http://localhost:8080/vlm"}, base)
    assert patched["vlm"] == "http://127.0.0.1:9090/vlm"
    assert patched["expression"] == "http://127.0.0.1:9090/expression"


def test_camera_gave_up_blocks_local_vision():
    """Verify real VisionProcessor.is_local_camera_available when camera hardware gave up."""
    from modules.vlm_bridge.services.processor import VisionProcessor

    proc = VisionProcessor({"vision": {"processing_mode": "local"}, "vision_llm": {"enabled": False}})
    proc._camera_hardware_available = True
    proc._camera_gave_up = True
    assert proc.is_local_camera_available() is False


def test_vision_event_bus_does_not_mutate_caller_dict():
    from modules.vlm_bridge.services.vision_event_bus import VisionEventBus

    bus = VisionEventBus()
    received = []
    bus.subscribe("test_ev", lambda et, d: received.append(d))

    caller_data = {"key": "value"}
    bus.publish("test_ev", caller_data)

    assert "event_type" not in caller_data, "caller dictionary must not be mutated in-place"
    assert len(received) == 1
    assert received[0]["event_type"] == "test_ev"
    assert received[0]["key"] == "value"
