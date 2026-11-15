"""Iteration 17 unit & contract tests for modules/agent_core/services/tools (Birim 31)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest
from modules.agent_core.services.expression_arbiter import ExpressionArbiter
from modules.agent_core.services.memory import EpisodicMemory
from modules.agent_core.services.safety_filter import ActionSafetyFilter
from modules.agent_core.services.slam import TopologicalMap
from modules.agent_core.services.tool_progress import tool_result_succeeded
from modules.agent_core.services.tools import HttpClient, ToolRegistry
from modules.agent_core.services.tools.tool_schemas import get_all_tool_definitions
from modules.agent_core.services.world_state import WorldState


def _make_registry(**kwargs) -> ToolRegistry:
    mem = EpisodicMemory(":memory:")
    slam = TopologicalMap.__new__(TopologicalMap)
    slam.map_file = "test_tools_it17.json"
    slam.nodes = {"base_station": {"neighbors": [], "description": "base"}}
    slam.aliases = {}
    slam.current_location = "base_station"
    ws = WorldState()
    sf = ActionSafetyFilter()
    return ToolRegistry(
        kwargs.pop("client", None),
        mem,
        slam,
        ws,
        sf,
        **kwargs,
    )


def test_all_tool_definitions_have_registered_methods_and_remember_fact_included():
    defs = get_all_tool_definitions()
    names = [d["function"]["name"] for d in defs]
    assert "remember_fact" in names
    assert "queue_action" in names
    assert "print_to_lcd" in names
    assert "get_last_rfid" in names

    reg = _make_registry()
    try:
        for name in names:
            assert name in reg.tools, f"Schema tool '{name}' missing on ToolRegistry"
            assert callable(reg.tools[name])
    finally:
        reg.close()


def test_execute_validates_required_types_and_filters_unexpected_kwargs():
    reg = _make_registry()
    try:
        # Missing required parameter on remember_fact
        res_missing = reg.execute("remember_fact", {})
        assert "missing required argument 'fact'" in res_missing

        # Wrong type (bool as integer rejected, int as string rejected)
        res_bad_int = reg.execute("move_head", {"pan": True, "tilt": 90})
        assert "must be integer" in res_bad_int
        res_bad_str = reg.execute("speak", {"text": 12345})
        assert "must be string" in res_bad_str

        # Unexpected extra kwargs stripped safely without TypeError
        res_extra = reg.execute("get_sensor_data", {"hallucinated": 999, "unused": "abc"})
        assert "Battery:" in res_extra
        assert "TypeError" not in res_extra
    finally:
        reg.close()


def test_express_emotion_render_none_clamp_intensity_and_arbiter(monkeypatch):
    expr_arbiter = ExpressionArbiter()
    action_arbiter = ActionArbiter()
    posted = []

    def _express_handler(req: ActionRequest):
        posted.append(req.payload)
        return {"ok": True, "data": {"ok": True}}

    action_arbiter.register_handler("express", _express_handler)
    reg = _make_registry(
        client=SimpleNamespace(ok=True),
        action_arbiter=action_arbiter,
        expression_arbiter=expr_arbiter,
    )
    try:
        monkeypatch.setattr(
            "modules.common.emotion_vocab.get_vocab",
            lambda: (_ for _ in ()).throw(RuntimeError("vocab missing")),
        )
        out = reg.express_emotion(emotion="joy", intensity=5.0, duration_s=2.0, modalities=["leds"])
        assert "Expressed joy" in out
        assert "intensity=2.00" in out
        assert posted and posted[0]["intensity"] == 2.0

        # When expression arbiter holds a higher manual lease, express_emotion skips
        expr_arbiter.claim_lights("manual_override", force=True, priority=95, ttl_s=5.0)
        skipped = reg.express_emotion(emotion="sadness", intensity=1.0, duration_s=2.0, modalities=["leds"])
        assert "skipped" in skipped.lower()
    finally:
        reg.close()


def test_remember_fact_and_search_memory_use_singleton_rag(monkeypatch):
    calls = {"get_default": 0, "observe": 0, "chat_ingest": 0}

    class StubWM:
        def observe(self, item, source=""):
            calls["observe"] += 1
            return {"ok": True}

        def recall(self, q, limit=4):
            return {"items": [{"kind": "objects", "name": "anahtar", "summary": "Mavi cekmecede", "rank_score": 0.9}]}

    class StubChatRag:
        def ingest(self, **_k):
            calls["chat_ingest"] += 1
            return True

        def recall(self, q, limit=4):
            return []

    monkeypatch.setattr(
        "modules.cognitive_memory.services.world_memory_rag.get_default",
        lambda: (calls.__setitem__("get_default", calls["get_default"] + 1) or StubWM()),
    )
    monkeypatch.setattr(
        "modules.cognitive_memory.services.chat_rag.get_default",
        lambda: StubChatRag(),
    )

    reg = _make_registry()
    try:
        res = reg.remember_fact("Anahtar cekmecede", category="objects", subject="anahtar")
        assert "world_memory_rag" in res
        # Objects category avoids redundant triple-write into ChatRAG when WorldMemoryRAG persisted
        assert calls["observe"] == 1
        assert calls["chat_ingest"] == 0

        found = reg.search_memory("anahtar")
        assert "Mavi cekmecede" in found
        assert calls["get_default"] == 2
    finally:
        reg.close()


def test_http_client_session_public_arduino_and_inprocess_action_arbiter():
    assert not hasattr(HttpClient, "_handle_response")
    http_client = HttpClient("http://127.0.0.1:8999")
    try:
        assert http_client._session is not None
    finally:
        http_client.close()

    # print_to_lcd / get_last_rfid call public HttpClient/client interface without _arduino_request
    sent = []
    client_obj = SimpleNamespace(
        arduino_request=lambda payload, timeout=1.0: (sent.append(payload) or {"ok": True, "rfid": "TAG-42"})
    )
    action_arbiter = ActionArbiter()
    queued = []
    action_arbiter.register_handler("speak", lambda req: (queued.append(req.payload) or {"queued": True}))

    reg = _make_registry(client=client_obj, action_arbiter=action_arbiter)
    try:
        lcd_out = reg.print_to_lcd("Merhaba", "Dünya")
        assert "Printed to LCD" in lcd_out
        rfid_out = reg.get_last_rfid()
        assert "TAG-42" in rfid_out
        assert len(sent) == 2

        q_res = reg.queue_action("speak", priority=60, payload={"text": "selam"})
        assert "Action queued:" in q_res
        assert queued == [{"text": "selam"}]
        assert "exclusive_locks" in reg.get_action_status()
        assert "'ok': True" in reg.cancel_action("act-1")
    finally:
        reg.close()


def test_vlm_timeout_fallback_not_treated_as_success():
    assert not tool_result_succeeded(
        "ask_vlm_about_scene",
        "Görüntü işleme gecikti; elimdeki son görüntüye göre konuşuyorum.",
    )


def test_dynamic_mcp_tools_adapter_and_per_tool_metrics():
    echo_tool = {
        "name": "ping",
        "description": "Ping external device",
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    }
    alive_conn = SimpleNamespace(alive=True, tools_cache=[echo_tool])
    offline_conn = SimpleNamespace(alive=False, tools_cache=[{"name": "ghost"}])
    mcp_client = MagicMock()
    mcp_client.enabled = True
    mcp_client._conns = {"diag": alive_conn, "offline": offline_conn}
    mcp_client.call.side_effect = [
        {"ok": True, "is_error": False, "text": "pong:cam1"},
        TimeoutError("mcp timed out"),
    ]

    reg = _make_registry(mcp_client=mcp_client)
    try:
        schemas = reg.get_tool_schema()
        schema_names = [s["function"]["name"] for s in schemas]
        assert "mcp__diag__ping" in schema_names
        assert "mcp__offline__ghost" not in schema_names

        subset = reg.get_tool_schema(include=["speak", "mcp__diag__ping"])
        assert [s["function"]["name"] for s in subset] == ["speak", "mcp__diag__ping"]

        ok_res = reg.execute("mcp__diag__ping", {"target": "cam1"})
        assert ok_res == "pong:cam1"

        err_res = reg.execute("mcp__diag__ping", {"target": "cam2"})
        assert "Error executing mcp__diag__ping" in err_res

        m = reg.metrics()["mcp__diag__ping"]
        assert m == {"calls": 2, "errors": 1, "timeouts": 1}
    finally:
        reg.close()
