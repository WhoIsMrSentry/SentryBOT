from __future__ import annotations

import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.vlm_bridge.api.analysis import get_analysis_router
from modules.vlm_bridge.services.ollama_vlm_client import OllamaVLMClient
from modules.vlm_bridge.services.processor import VisionProcessor


def test_processor_collect_ask_context_hints_and_ocr_vlm_fallback():
    proc = VisionProcessor.__new__(VisionProcessor)
    proc.latest_results = [
        {"label": "person", "name": "Emir"},
        {"label": "person", "name": "Unknown"},
        {"label": "laptop"},
    ]
    proc.face_manager = None
    proc.processing_mode = "local"
    proc.visual_context_cache = None

    hints = proc.collect_ask_context_hints(frame=None)
    assert "Emir" in hints
    assert "Unknown" not in hints
    assert "laptop" in hints

    # Remote OCR disabled -> fallback cleanly to OllamaVLMClient.extract_text_ocr
    proc.mode_categories = {"remote": {"ocr": False}}
    proc.mode_flags = {"ocr": True}
    proc.remote_mm_enabled = False
    proc.remote_mm_ocr_endpoint = ""
    proc.remote_mm_ocr_timeout_s = 1.0
    proc.remote_mm_ocr_languages = ["tr", "en"]
    proc.remote_mm_auth_token = ""
    proc._grab_frame = lambda: object()

    client = OllamaVLMClient({"base_url": "http://127.0.0.1:11434", "min_interval_s": 0})
    captured_prompts = []
    client._call_ollama = lambda prompt, _b64: (
        captured_prompts.append(prompt) or {"raw_text": "Satir 1: Emir\nSatir 2: SentryBOT"}
    )
    import modules.vlm_bridge.services.ollama_vlm_client as mod

    old_encode = mod._resize_and_encode
    mod._resize_and_encode = lambda _f, max_width=640, jpeg_quality=70: "ZmFrZQ=="
    try:
        proc.vlm_client = client
        ocr_res = proc.run_ocr_remote()
        assert ocr_res["ok"] is True
        assert ocr_res["source"] == "vlm_ocr_fallback"
        assert "Emir" in ocr_res["text"]
        assert len(ocr_res["lines"]) == 2
        assert captured_prompts
    finally:
        mod._resize_and_encode = old_encode


def test_vlm_ask_passes_context_hints_to_client():
    asked = {}

    class _FakeVLM:
        @staticmethod
        def ask_about_scene(frame, question, force=True, *, context_hints=None):
            asked["question"] = question
            asked["context_hints"] = context_hints
            asked["force"] = force
            return "Kamerada Emir gorunuyor."

    proc = SimpleNamespace(
        is_local_camera_available=lambda: True,
        _grab_frame=lambda: object(),
        _frame_lock=threading.Lock(),
        _latest_raw_frame=object(),
        _is_http_camera_source=lambda: False,
        collect_ask_context_hints=lambda _frame=None: "Tanınan yüzler: Emir",
        vlm_client=_FakeVLM(),
        vision_request_gate=None,
    )
    app = FastAPI()
    app.include_router(get_analysis_router(proc, "http://127.0.0.1:8080"))
    client = TestClient(app)

    resp = client.post("/ask", json={"question": "kameradaki kisi kim?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["hints_used"] is True
    assert asked["context_hints"] == "Tanınan yüzler: Emir"
