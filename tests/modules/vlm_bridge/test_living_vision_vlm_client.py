import threading
import time


def test_vlm_json_parse_fallback_works():
    from modules.vlm_bridge.services.ollama_vlm_client import _parse_vlm_json

    text = "Sonuc:\n```json\n{\"summary\":\"oda\",\"objects\":[]}\n```"
    parsed = _parse_vlm_json(text)

    assert parsed.get("summary") == "oda"
    assert "raw_text" in parsed


def test_concurrent_vlm_calls_are_deduplicated():
    from modules.vlm_bridge.services.ollama_vlm_client import OllamaVLMClient

    client = OllamaVLMClient(
        {
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen3-vl:8b",
            "min_interval_s": 0,
        }
    )

    def fake_call(_prompt, _image_b64):
        time.sleep(0.08)
        return {"summary": "ok", "raw_text": "ok"}

    def fake_encode(_frame, max_width=640, jpeg_quality=70):
        return "ZmFrZQ=="

    # monkeypatch without pytest fixture dependency
    import modules.vlm_bridge.services.ollama_vlm_client as mod

    old_call = client._call_ollama
    old_encode = mod._resize_and_encode
    client._call_ollama = fake_call
    mod._resize_and_encode = fake_encode
    try:
        results = []

        def worker():
            results.append(client.analyze_frame(frame=object(), force=True))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    finally:
        client._call_ollama = old_call
        mod._resize_and_encode = old_encode

    assert sum(1 for r in results if r is not None) == 1
