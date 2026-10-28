import pytest

from modules.agent_core.services.laya_engine import LayaEngine
from modules.agent_core.services.system1_cascade import System1CascadeEngine


@pytest.fixture
def cascade_engine():
    LayaEngine._instance = None
    System1CascadeEngine._instance = None
    cfg = {
        "tri_layer": {"system1": {"backend": "cascade", "enabled": True, "embed": {"enabled": False}}}
    }
    engine = LayaEngine.get_instance(cfg)
    yield engine
    System1CascadeEngine._instance = None


def test_factory_returns_cascade(cascade_engine):
    assert type(cascade_engine).__name__ == "System1CascadeEngine"
    assert cascade_engine.laya is LayaEngine.get_instance(laya_config(), raw=True)


def laya_config():
    return {"tri_layer": {"system1": {"backend": "laya"}}}


def test_rules_tier_short_circuits(cascade_engine):
    decision = cascade_engine.decide("hemen dur")
    assert decision is not None
    assert (decision.raw_answers or {}).get("backend") == "rules"
    assert decision.target_module == "emergency_stop"


def test_should_fast_path_direct_and_emergency(cascade_engine):
    ok, _ = cascade_engine.should_fast_path("hemen dur")
    assert ok is True
    ok, _ = cascade_engine.should_fast_path("ışığı kırmızı yap")
    assert ok is True
    ok, _ = cascade_engine.should_fast_path("bugün hava nasıl güzel")
    assert ok is False


def test_filler_and_affect_delegate(cascade_engine):
    assert cascade_engine.get_fast_ack("tr")
    reaction = cascade_engine.get_affective_reaction("praise")
    assert reaction["emotion"] == "joy"


def test_backend_switch_without_cascade():
    LayaEngine._instance = None
    System1CascadeEngine._instance = None
    cfg = {"tri_layer": {"system1": {"backend": "laya"}}}
    engine = LayaEngine.get_instance(cfg)
    assert type(engine).__name__ == "LayaEngine"
    System1CascadeEngine._instance = None


def test_onnx_semantic_router_indirect_turkish_and_affect():
    from modules.agent_core.services.system1_embed import System1EmbedEngine

    eng = System1EmbedEngine.get_instance()
    if not eng.is_available:
        pytest.skip("ONNX model not available")

    # Indirect lighting request
    d_dark = eng.decide("ortam zifiri karanlık hiçbir şey göremiyorum")
    assert d_dark is not None
    assert d_dark.target_module == "neopixel"
    assert d_dark.is_direct_command is True

    # Indirect collision hazard -> emergency_stop
    d_wall = eng.decide("önünde duvar var dikkat et")
    assert d_wall is not None
    assert d_wall.target_module == "emergency_stop"
    assert d_wall.is_direct_command is True
    assert d_wall.is_emergency is True

    # Indirect head/motor orientation
    d_sound = eng.decide("sol taraftan bir tıkırtı geldi oraya bak")
    assert d_sound is not None
    assert d_sound.target_module == "arduino_serial"
    assert d_sound.is_direct_command is True

    # Indirect camera inspection
    d_cam = eng.decide("masanın üstünde ne var kontrol et")
    assert d_cam is not None
    assert d_cam.target_module == "camera"
    assert d_cam.is_direct_command is True

    # Semantic affect classification (disgust & joy)
    d_disgust = eng.decide("midem bulandı çok iğrenç kokuyor")
    assert d_disgust is not None
    assert d_disgust.affective_event == "disgust"
    assert d_disgust.is_direct_command is False

    d_joy = eng.decide("içim kıpır kıpır harika bir gün")
    assert d_joy is not None
    assert d_joy.affective_event == "joy"
    assert d_joy.is_direct_command is False


def test_shared_singleton_embed_engine():
    from modules.agent_core.services.system1_embed import System1EmbedEngine

    LayaEngine._instance = None
    System1CascadeEngine._instance = None
    cfg = {
        "tri_layer": {"system1": {"backend": "cascade", "enabled": True, "embed": {"enabled": True}}}
    }
    cascade = LayaEngine.get_instance(cfg)
    assert cascade.embed is System1EmbedEngine.get_instance()
    System1CascadeEngine._instance = None


def test_indirect_turkish_action_hints():
    from modules.agent_core.services.system1_embed import System1EmbedEngine

    eng = System1EmbedEngine.get_instance()
    if not eng.is_available:
        pytest.skip("ONNX model not available")

    d_dark = eng.decide("ortam zifiri karanlık hiçbir şey göremiyorum")
    assert d_dark is not None
    hint = (d_dark.raw_answers or {}).get("action_hint")
    assert hint == {"tool": "set_lights", "color": "white", "effect": "SOLID"}

    d_left = eng.decide("sol taraftan bir tıkırtı geldi oraya bak")
    assert d_left is not None
    hint_left = (d_left.raw_answers or {}).get("action_hint")
    assert hint_left == {"tool": "move_head", "direction": "left"}


def test_turkish_semantic_index_inflection_matching():
    from modules.agent_core.services.semantic_index import rank

    docs = [
        "Bugün hava oldukça güneşli ve sıcak.",
        "Gözlüklerimi mutfak masasının üstüne bıraktım.",
        "Kitapları üst rafa dizdim.",
    ]
    # "gözlüğüm" (inflected with consonant softening k->ğ) must match "Gözlüklerimi..."
    hits = rank("Gözlüğüm nerede?", docs, top_k=1)
    assert hits and hits[0][0] == 1

    # "kitabım" (inflected with consonant softening p->b) must match "Kitapları..."
    hits_book = rank("Kitabım hangi rafta?", docs, top_k=1)
    assert hits_book and hits_book[0][0] == 2


def test_turkish_sov_preference_and_fact_extraction():
    from modules.cognitive_memory.services.preference_learner import PreferenceLearner

    learner = PreferenceLearner()
    prefs = learner.extract_preferences("Türk kahvesini çok seviyorum. Gürültüyü hiç sevmiyorum.")
    assert any("kahve" in x for x in prefs["likes"])
    assert any("gürültü" in x for x in prefs["dislikes"])

    facts = learner.extract_facts("Benim adım Emir, kedimin adı Pamuk ve Ankara'da yaşıyorum.")
    assert "user name is Emir" in facts
    assert "user has a pet named Pamuk" in facts
    assert "user lives in Ankara" in facts


def test_chat_rag_zero_keyword_overlap_semantic_recall(tmp_path):
    from modules.cognitive_memory.services.chat_rag import ChatRAG
    from modules.agent_core.services.system1_embed import System1EmbedEngine

    eng = System1EmbedEngine.get_instance()
    if not eng.is_available:
        pytest.skip("ONNX model not available")

    rag = ChatRAG({"enabled": True, "db_path": str(tmp_path / "rag.sqlite3")})
    rag.set_embedding_provider(eng.embed_vector)

    rag.ingest(person_id="emir", role="user", text="Hava bugün biraz rüzgarlı.")
    rag.ingest(person_id="emir", role="user", text="Kedimin adı Pamuk, bembeyaz bir İran kedisi.")
    rag.ingest(person_id="emir", role="user", text="Yarın saat 10'da toplantım var.")

    # Query uses inflected/synonym words ("Kedilerimden ismi neydi?") with zero exact FTS5 token match
    recalled = rag.recall("Kedilerimden ismi neydi?", person_id="emir", limit=2)
    assert recalled
    assert "Pamuk" in recalled[0]["text"]


def test_remember_fact_and_multi_store_search_memory(tmp_path, monkeypatch):
    from modules.agent_core.services.memory import EpisodicMemory
    from modules.agent_core.services.tools.social_tools import SocialToolsMixin

    class _DummyRegistry(SocialToolsMixin):
        def __init__(self, mem):
            self.memory = mem
            self.client = None

    reg = _DummyRegistry(EpisodicMemory(":memory:"))
    out = reg.remember_fact(
        fact="Yedek anahtar mavi çekmecenin içinde duruyor.",
        category="objects",
        subject="yedek_anahtar",
    )
    assert "Remembered" in out

    found = reg.search_memory("Yedek anahtar nerede?")
    assert "mavi çekmecenin" in found


