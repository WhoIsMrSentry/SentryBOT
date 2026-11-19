"""Tests for PersonaRAG, two-layer prompts, model switching, voice commands, and TTS voice override."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from modules.agent_core.api.persona import get_persona_router as get_agent_persona_router
from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.tools.tool_registry import ToolRegistry
from modules.ai_provider.services.persona_rag import PersonaManager, PersonaRAG
from modules.autonomy.services.brain_parts.speech_react import SpeechReactMixin
from modules.autonomy.services.brain_parts.vocal import VocalMixin
from modules.autonomy.services.brain_parts.vocal_prosody import VocalProsodyMixin
from modules.common.ollama_modelfile import (
    DEFAULT_BASE_MODEL,
    build_ollama_create_payload,
    parse_modelfile,
)
from modules.common.persona_scope import DEFAULT_PERSONA_ID, set_active_persona
from modules.common.system_prompts import persona_prompt_with_language
from modules.common.web_extractor import extract_html_title, extract_readable_text
from modules.voice.speak.services.tts import TextToSpeech
from modules.voice.speak.xSpeakService import SpeakService


@pytest.fixture(autouse=True)
def _reset_persona():
    set_active_persona(DEFAULT_PERSONA_ID, notify=False)
    yield
    set_active_persona(DEFAULT_PERSONA_ID, notify=False)


def test_real_glados_and_sentry_personas_and_rag_recall(tmp_path: Path, monkeypatch) -> None:
    mgr = PersonaManager("modules/ai_provider/config/personalities")
    try:
        items = mgr.list_personas()
        ids = {item["id"] for item in items}
        assert {"sentry", "glados"} <= ids
        assert mgr.resolve_name("gla-dos") == "glados"

        glados_data = mgr.load_persona("glados")
        assert "GLaDOS" in glados_data["prompt_text"]
        assert "🍰[ROLE]" in glados_data["prompt_text"]
        assert glados_data["manifest"]["model"] == "glados:latest"
        assert glados_data["manifest"]["base_model"] == DEFAULT_BASE_MODEL
        assert glados_data["manifest"]["tts_voice_en"] == "glados"

        # Exact 52 theportalwiki URLs matching WhoIsMrSentry/GLaDOS_Voice
        real_glados_urls = Path("modules/ai_provider/config/personalities/glados/urls.txt").read_text(encoding="utf-8").splitlines()
        real_glados_urls = [u.strip() for u in real_glados_urls if u.strip()]
        assert len(real_glados_urls) == 52
        assert all(u.startswith("https://theportalwiki.com/wiki/") for u in real_glados_urls)

        # Both sentry/modelfile and glados/modelfile derive from nemotron-3.5-bolt:e4b
        for pname, expected_marker in (("sentry", "SentryBOT"), ("glados", "GLaDOS")):
            mf_txt = Path(f"modules/ai_provider/config/personalities/{pname}/modelfile").read_text(encoding="utf-8")
            parsed = parse_modelfile(mf_txt)
            assert parsed["from"] == DEFAULT_BASE_MODEL
            assert parsed["renderer"] == "gemma4-nemotron"
            assert parsed["parser"] == "gemma4"
            assert expected_marker in parsed["system"]

        # MediaWiki Portal Wiki HTML preprocessor matches wiki_llamaindex_preprocess cut-offs
        fake_html = (
            "<html><head><title>Cave Johnson - Portal Wiki</title></head><body>"
            "<div id=\"mw-content-text\">"
            "<h1>Cave Johnson</h1>"
            "<p>Cave Johnson founded Aperture Science Innovators in 1943.</p>"
            "<h2>Gallery</h2><p>Image captions</p>"
            "</div></body></html>"
        )
        assert extract_html_title(fake_html) == "Cave Johnson"
        cleaned_md = extract_readable_text(fake_html, strip_mediawiki_noise=True)
        assert "Aperture Science Innovators" in cleaned_md
        assert "Image captions" not in cleaned_md

        # Query fetched wiki content inside a temporary copy so test leaves repo untouched
        test_dir = tmp_path / "glados"
        test_dir.mkdir(parents=True)
        (test_dir / "urls.txt").write_text("https://theportalwiki.com/wiki/Cave_Johnson\n", encoding="utf-8")
        monkeypatch.setattr(
            "modules.ai_provider.services.persona_rag.fetch_url_text",
            lambda url, **kw: {
                "ok": True,
                "url": url,
                "title": "Cave Johnson",
                "text": "Cave Johnson founded Aperture Science Innovators and created Wheatley in Aperture lore.",
            },
        )
        rag = PersonaRAG(test_dir)
        try:
            res = rag.ingest(fetch_urls=True, resolve_dns=False)
            assert res["ok"] is True
            assert res["fetched"] == 1
            assert res["chunks_total"] >= 1
            assert any(p.name.startswith("Cave_Johnson_") for p in (test_dir / "knowledge").glob("*.md"))

            ctx = rag.build_prompt_context("Who is Cave Johnson?", limit=3)
            assert "PERSONA LORE & KNOWLEDGE" in ctx
            assert "Cave Johnson" in ctx
        finally:
            rag.close()

        prompt = persona_prompt_with_language(
            glados_data["prompt_text"],
            "The user is speaking English. Reply ONLY in English.",
            lore_context="[PERSONA LORE] Aperture Science",
        )
        assert "EMBODIED ROBOT HARDWARE" in prompt
        assert "express_emotion" in prompt
        assert "control_laser" in prompt
        assert "GLaDOS" in prompt
    finally:
        mgr.close()


def test_agent_orchestrator_persona_switch_model_history_and_tools(tmp_path: Path, monkeypatch) -> None:
    cfg = {
        "agent": {
            "model": "sentry:latest",
            "temperature": 0.15,
            "personalities_dir": str(tmp_path),
            "persona": "sentry",
        },
        "models": {
            "single_model_mode": False,
            "roles": {
                "chat": "sentry:latest",
                "persona": "sentry:latest",
                "summarization": "nemotron-3.5-bolt:e4b",
                "coder": "nemotron-3.5-bolt:e4b",
            },
        },
        "tri_layer": {"enabled": False, "persona": {"system_prompt": ""}},
        "translation": {"enabled": False},
    }
    # Seed temporary persona folders
    for pname, ptxt, yml in (
        ("sentry", "You are SentryBOT.", "id: sentry\ndisplay_name: SentryBOT\n"),
        (
            "glados",
            "You are GLaDOS.",
            "id: glados\ndisplay_name: GLaDOS\ntts_voice_en: glados\naliases:\n  - glados\n",
        ),
    ):
        pdir = tmp_path / pname
        (pdir / "knowledge").mkdir(parents=True)
        (pdir / "persona.txt").write_text(ptxt, encoding="utf-8")
        (pdir / "persona.yml").write_text(yml, encoding="utf-8")
    (tmp_path / "glados" / "knowledge" / "lore.md").write_text(
        "# Wheatley\nWheatley is an Intelligence Dampening Sphere created to hamper GLaDOS.",
        encoding="utf-8",
    )

    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.config = cfg
    agent.model = "sentry:latest"
    agent.max_history = 10
    agent.chat_history = []
    agent.tool_registry = MagicMock()
    agent._init_persona_runtime(cfg)

    try:
        assert agent.active_persona == "sentry"
        assert agent._get_active_persona_model("Hello Sentry") == "sentry:latest"
        agent._append_history("user", "Sentry conversation turn")

        # Switch to GLaDOS -> model switches to derived glados:latest & history isolates
        state = agent.apply_persona("glados", response_language="en", trigger_emotion=False)
        assert state["persona"] == "glados"
        assert state["model"] == "glados:latest"
        assert agent._get_active_persona_model("Hello GLaDOS") == "glados:latest"
        assert agent.chat_history == []
        assert agent.effective_tts_voice("en") == "glados"
        assert agent.effective_tts_voice("tr") is None

        # Remote Ollama check: if glados:latest is absent and auto-create fails, fall back cleanly to nemotron
        agent.ollama_client = object()
        agent._list_ollama_models = lambda: ["sentry:latest", DEFAULT_BASE_MODEL]  # type: ignore[method-assign]
        agent.ollama_base_url = ""
        assert agent._get_active_persona_model("Who are you?") == DEFAULT_BASE_MODEL

        # When glados:latest IS present on remote Ollama PC, use glados:latest
        agent._list_ollama_models = lambda: ["sentry:latest", "glados:latest", DEFAULT_BASE_MODEL]  # type: ignore[method-assign]
        assert agent._get_active_persona_model("Who are you?") == "glados:latest"
        agent.ollama_client = None

        agent._append_history("user", "What is Wheatley?")
        msgs = agent._native_loop_messages("en")
        assert "Wheatley" in msgs[0]["content"]
        assert "GLaDOS" in msgs[0]["content"]
        assert "EMBODIED ROBOT HARDWARE" in msgs[0]["content"]

        # Switch back to Sentry -> restores Sentry chat history & sentry:latest model
        agent.apply_persona("sentry", trigger_emotion=False)
        assert agent._get_active_persona_model("Hi") == "sentry:latest"
        assert [m["content"] for m in agent.chat_history] == ["Sentry conversation turn"]

        # Native tools on ToolRegistry preserve both persona switching and robot hardware control
        reg = ToolRegistry(
            client=MagicMock(),
            memory=MagicMock(),
            slam=MagicMock(),
            world_state=MagicMock(),
            safety_filter=MagicMock(),
            persona_manager=agent.persona_manager,
            apply_persona_fn=lambda name, lang="": agent.apply_persona(name, response_language=lang, trigger_emotion=False),
        )
        try:
            names = [s["function"]["name"] for s in reg.schemas]
            assert {"set_persona", "list_personas", "search_persona_knowledge", "express_emotion", "control_laser", "web_search"} <= set(names)
            assert "glados" in reg.set_persona("glados", response_language="en")
            assert "glados *" in reg.list_personas()
            assert "Intelligence Dampening Sphere" in reg.search_persona_knowledge("Wheatley")
        finally:
            reg.close()

        # Agent Core HTTP persona endpoints + dynamic persona creation pushing Modelfile to remote Ollama PC
        pushed_models = []
        monkeypatch.setattr(
            "modules.common.ollama_modelfile.create_remote_ollama_model",
            lambda name, mf, **kw: pushed_models.append((name, build_ollama_create_payload(name, mf), kw.get("base_url"))) or (True, "ok"),
        )
        agent.ollama_base_url = "http://whoismrsentry.local:11434"
        app = FastAPI()
        app.include_router(get_agent_persona_router(agent), prefix="/agent")
        client = TestClient(app)
        assert client.get("/agent/persona").json()["persona"] == "glados"
        r_create = client.post(
            "/agent/persona/create",
            json={
                "name": "hal9000",
                "instructions": "You are HAL 9000.",
                "default_emotion": "curiosity",
                "create_model": True,
                "fetch_urls": False,
            },
        )
        assert r_create.status_code == 200
        assert r_create.json()["model"] == "hal9000:latest"
        assert pushed_models[0][0] == "hal9000:latest"
        assert pushed_models[0][1]["from"] == DEFAULT_BASE_MODEL
        assert pushed_models[0][1]["renderer"] == "gemma4-nemotron"
        assert pushed_models[0][2] == "http://whoismrsentry.local:11434"
        assert (tmp_path / "hal9000" / "modelfile").is_file()
        assert client.get("/agent/persona").json()["model"] == "hal9000:latest"
        assert client.post("/agent/persona/select", json={"name": "sentry"}).json()["persona"] == "sentry"
    finally:
        agent._close_persona_runtime()


def test_voice_command_persona_switch_and_tts_glados_voice(tmp_path: Path) -> None:
    import shutil

    personas_copy = tmp_path / "personalities"
    for p in ("sentry", "glados"):
        shutil.copytree(Path("modules/ai_provider/config/personalities") / p, personas_copy / p, ignore=shutil.ignore_patterns("*.sqlite3*"))

    class _DummyBrain(VocalMixin, SpeechReactMixin, VocalProsodyMixin):
        def __init__(self) -> None:
            self.config = {"companion": {"emotion_command_shortcut": True}}
            self.state = {"last_speech_language": "tr"}
            self.mood = SimpleNamespace(get_dominant_emotion=lambda: "neutral", modify=lambda *a, **kw: None)
            self.memory = MagicMock()
            self.client = MagicMock()
            self._speech_req_lock = MagicMock()
            self._speech_req_lock.__enter__ = lambda s: None
            self._speech_req_lock.__exit__ = lambda s, *a: None
            self._active_speech_req_id = "r1"
            self._speech_busy = False
            self.spoken = []
            self.agent = SimpleNamespace(
                persona_manager=PersonaManager(personas_copy),
                apply_persona=self._apply,
            )

        def _apply(self, name: str, response_language: str = "", trigger_emotion: bool = True):
            loaded = self.agent.persona_manager.load_persona(name)
            manifest = dict(loaded["manifest"])
            if response_language:
                manifest["response_language"] = response_language
            set_active_persona(loaded["name"], meta=manifest)
            return {"persona": loaded["name"], "meta": manifest}

        def _speak_with_mood(self, text: str, emotion: str | None = None, language: str | None = None, voice: str | None = None) -> None:
            self.spoken.append({"text": text, "emotion": emotion, "language": language, "voice": voice})

        def express(self, emotion: str, say: str = "", language: str = "tr"):
            self.spoken.append({"emotion_cmd": emotion, "say": say, "language": language})
            return emotion

        def _normalize_emotion_name(self, c: str) -> str:
            return c

        def _run_scene(self, *a, **kw):
            pass

    brain = _DummyBrain()
    try:
        # Normal question must NOT falsely switch persona
        assert brain._parse_persona_voice_command("GLaDOS kimdir?") is None

        # Turkish switch to GLaDOS
        assert brain._handle_speech_command_shortcuts("glados moduna geç", "tr", "r1") is True
        assert brain.state["active_persona"] == "glados"
        assert brain.spoken[-1]["language"] == "tr"
        assert brain.spoken[-1]["voice"] is None

        # Emotion shortcut while GLaDOS is active speaks in GLaDOS style + drives hardware emotion
        assert brain._handle_speech_command_shortcuts("sinirlen", "tr", "r1") is True
        assert brain.spoken[-1]["emotion_cmd"] == "anger"
        assert "çekirdeğim" in brain.spoken[-1]["say"].lower() or "nörotoksin" in brain.spoken[-1]["say"].lower() or "öfke" in brain.spoken[-1]["say"].lower()

        # English GLaDOS switch forces Piper voice='glados'
        assert brain._handle_speech_command_shortcuts("glados ingilizce moduna geç", "tr", "r1") is True
        assert brain.spoken[-1]["language"] == "en"
        assert brain.spoken[-1]["voice"] == "glados"

        # Return to Sentry when GLaDOS active
        assert brain._handle_speech_command_shortcuts("normale dön", "tr", "r1") is True
        assert brain.state["active_persona"] == "sentry"

        # Now when already Sentry, 'normale dön' reverts to neutral emotion shortcut
        assert SpeechReactMixin._parse_persona_voice_command("normale dön") is None
        assert SpeechReactMixin._emotion_command_for_text("normale dön") == "neutral"
    finally:
        brain.agent.persona_manager.close()

    # Piper explicit voice selection takes priority in TextToSpeech._resolve_piper_voice
    tts = object.__new__(TextToSpeech)
    piper_cfg = {
        "auto_language": True,
        "language_voices": {"tr": "tr", "en": "glados"},
        "voices": {"tr": {"model_path": "tr.onnx"}, "glados": {"model_path": "glados.onnx"}},
    }
    assert tts._resolve_piper_voice("Merhaba dünya", {"language": "tr", "piper": piper_cfg}, {"voice": "glados"}) == "glados"


def test_build_persona_rag_cli_script_and_tts_emoji_strip(tmp_path: Path, monkeypatch) -> None:
    from scripts.setup.build_persona_rag import main as build_rag_main

    pdir = tmp_path / "glados"
    (pdir / "knowledge").mkdir(parents=True)
    (pdir / "persona.txt").write_text("You are GLaDOS.", encoding="utf-8")
    (pdir / "knowledge" / "lore.md").write_text("# Aperture\nBorealis is a missing Aperture vessel.", encoding="utf-8")

    pushed = []
    monkeypatch.setattr(
        "modules.common.ollama_modelfile.create_remote_ollama_model",
        lambda name, mf, **kw: pushed.append((name, kw.get("base_url"))) or (True, "ok"),
    )

    rc = build_rag_main(
        ["--persona", "glados", "--base-dir", str(tmp_path), "--create-models", "--ollama-url", "http://whoismrsentry.local:11434"]
    )
    assert rc == 0
    assert (pdir / "persona_rag.sqlite3").is_file()
    assert pushed == [("glados:latest", "http://whoismrsentry.local:11434")]

    # GLaDOS signature emojis are stripped cleanly before Piper TTS while Turkish letters stay intact
    cleaned = SpeakService._clean_text_for_speech("🍰Buy some neurotoxin. Merhaba Türkçe🤞")
    assert cleaned == "Buy some neurotoxin. Merhaba Türkçe"
