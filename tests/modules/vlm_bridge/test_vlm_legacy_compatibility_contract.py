from __future__ import annotations

import types

from modules.vlm_bridge.services import processor
from modules.vlm_bridge.services.llm_client import (
    VLM_LLM_LEGACY_ENDPOINT_COMPATIBILITY_CONTRACT,
    VLM_LLM_LEGACY_ENDPOINT_ROLE,
    _derive_chat_endpoint_from_base_url,
    _is_legacy_generate_endpoint,
)
from modules.cognitive_memory.services.people_memory import (
    PeopleMemory,
    VLM_PEOPLE_MEMORY_COMPATIBILITY_CONTRACT,
    VLM_PEOPLE_MEMORY_ROLE,
)
from modules.vlm_bridge.services.person_identity import (
    PersonIdentityManager,
    VLM_PERSON_IDENTITY_COMPATIBILITY_CONTRACT,
    VLM_PERSON_IDENTITY_ROLE,
)


def test_vlm_llm_legacy_generate_endpoint_is_explicit_compatibility():
    assert VLM_LLM_LEGACY_ENDPOINT_COMPATIBILITY_CONTRACT is True
    assert VLM_LLM_LEGACY_ENDPOINT_ROLE == "ollama_generate_to_chat_compatibility_adapter"
    assert _is_legacy_generate_endpoint("http://127.0.0.1:11434/api/generate") is True
    assert _is_legacy_generate_endpoint("http://127.0.0.1:11434/api/chat") is False
    assert _derive_chat_endpoint_from_base_url("http://127.0.0.1:11434/api/tags").endswith("/api/chat")


def test_people_memory_json_path_is_backward_compatibility_store(tmp_path):
    assert VLM_PEOPLE_MEMORY_COMPATIBILITY_CONTRACT is True
    assert VLM_PEOPLE_MEMORY_ROLE == "social_db_primary_json_backward_compatibility_store"
    memory = PeopleMemory(data_dir=str(tmp_path), filename="people_memory.json", social_db=None)
    memory.append_chat("Emir", "user", "merhaba")
    memory.set_summary("Emir", "owner profile")
    reloaded = PeopleMemory(data_dir=str(tmp_path), filename="people_memory.json", social_db=None)
    rec = reloaded.get_person("Emir")
    assert rec is not None
    assert rec["chats"][0]["text"] == "merhaba"
    assert rec["last_summary"]["text"] == "owner profile"


def test_person_identity_json_path_is_backward_compatibility_store(tmp_path):
    assert VLM_PERSON_IDENTITY_COMPATIBILITY_CONTRACT is True
    assert VLM_PERSON_IDENTITY_ROLE == "social_db_primary_person_json_compatibility_store"
    store = tmp_path / "person_identity.json"
    manager = PersonIdentityManager(store_path=str(store), social_db=None)
    rec = manager.remember_person("Emir", relationship="owner", recognition_level=5)
    assert rec.owner_priority is True
    reloaded = PersonIdentityManager(store_path=str(store), social_db=None)
    assert reloaded.is_owner("Emir") is True


def test_processor_cv2_legacy_tracker_is_explicit_compatibility(monkeypatch):
    assert processor.VLM_PROCESSOR_LEGACY_COMPATIBILITY_CONTRACT is True
    assert processor.VLM_PROCESSOR_LEGACY_COMPATIBILITY_ROLE == "opencv_api_and_cached_context_compatibility"

    class ModernCV2:
        @staticmethod
        def TrackerCSRT_create():
            return "modern"

    monkeypatch.setattr(processor, "cv2", ModernCV2)
    assert processor._create_csrt_tracker() == "modern"

    legacy = types.SimpleNamespace(TrackerCSRT_create=lambda: "legacy")
    monkeypatch.setattr(processor, "cv2", types.SimpleNamespace(legacy=legacy))
    assert processor._create_csrt_tracker() == "legacy"
