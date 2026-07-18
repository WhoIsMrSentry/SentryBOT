# SentryBOT Pi Runtime Stub/Legacy Caller Audit

Generated: `2026-07-18T15:34:12`

Target: Pi/Linux robot runtime. PC remains only the development/test host.

Report-only. No code changed and no hardware/camera/VLM/motion was started.

Purpose: identify stub/dummy/fake/legacy/deprecated/fallback surfaces and their callers before cleanup.

## Summary

| metric | value |
| --- | --- |
| target | Pi/Linux robot runtime |
| pc_is_dev_host_only | True |
| files_scanned | 568 |
| records_with_terms | 103 |
| runtime_replacement_candidate_files | 2 |
| compatibility_review_files | 29 |
| documentation_files | 21 |
| config_review_files | 2 |
| severity_counts | {"config_review": 27, "review": 199, "documentation": 43, "expected_degraded_path": 39, "runtime_replacement_candidate": 34, "compatibility_review": 32, "expected_test_or_preview": 16} |
| term_counts | {"dummy": 8, "fallback": 78, "noop": 5, "legacy": 27, "fake": 2, "deprecated": 3, "no-op": 3, "placeholder": 3, "mock": 2} |

## Runtime Replacement Candidates

| path | terms | severities | callers | known_review |
| --- | --- | --- | --- | --- |
| modules/autonomy/services/capability_executor.py | fallback, noop | {"review": 1, "runtime_replacement_candidate": 1} | 3 | False |
| modules/speak/services/tts.py | dummy, fallback, legacy | {"expected_test_or_preview": 10, "review": 5, "runtime_replacement_candidate": 4} | 34 | False |

### `modules/autonomy/services/capability_executor.py`

| line | term | severity | kind | context | text |
| --- | --- | --- | --- | --- | --- |
| 106 | fallback | review | code_or_text | FunctionDef:_dispatch | text = str(params.get("text") or capability.get("fallback_text") or "").strip() |
| 120 | noop | runtime_replacement_candidate | code_or_text | FunctionDef:_dispatch | if handler in {"wait", "semantic_noop"}: |

Text references:

| from_path | line | key | snippet |
| --- | --- | --- | --- |
| modules/autonomy/services/companion_goal_executor.py | 6 | capability_executor | 0005: <br>0006: from .capability_executor import CapabilityExecutor<br>0007:  |
| modules/autonomy/services/companion_goal_executor.py | 38 | capability_executor | 0037:             "stop_on_failure": self.stop_on_failure,<br>0038:             "capability_executor": (<br>0039:                 self.capabilities.status() |
| modules/autonomy/services/companion_goal_executor.py | 122 | capability_executor | 0121:                 False,<br>0122:                 "dry_run" if effective_dry_run else "capability_executor_unavailable",<br>0123:                 plan, |

### `modules/speak/services/tts.py`

| line | term | severity | kind | context | text |
| --- | --- | --- | --- | --- | --- |
| 78 | dummy | expected_test_or_preview | code_or_text | ClassDef:DummyBackend | class DummyBackend(TTSBackend): |
| 110 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_dummy_allowed | def _dummy_allowed(cfg: Dict[str, Any]) -> bool: |
| 111 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_dummy_allowed | requested = bool(cfg.get("allow_dummy_fallback", False)) |
| 111 | fallback | review | code_or_text | FunctionDef:_dummy_allowed | requested = bool(cfg.get("allow_dummy_fallback", False)) |
| 241 | legacy | runtime_replacement_candidate | code_or_text | FunctionDef:_synthesize_legacy_stream | def _synthesize_legacy_stream(self, text: str, values: Dict[str, Any]) -> Optional[PCM]: |
| 265 | legacy | runtime_replacement_candidate | code_or_text | FunctionDef:_synthesize_legacy_wav | def _synthesize_legacy_wav(self, text: str, values: Dict[str, Any]) -> PCM: |
| 295 | legacy | runtime_replacement_candidate | code_or_text | FunctionDef:synthesize | pcm = self._synthesize_legacy_stream(text, values) |
| 297 | legacy | runtime_replacement_candidate | code_or_text | FunctionDef:synthesize | pcm = self._synthesize_legacy_wav(text, values) |
| 449 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_build_backend | if tcfg.engine == "dummy": |
| 450 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_build_backend | if _dummy_allowed(cfg): |
| 451 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_build_backend | return DummyBackend(tcfg) |
| 452 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_build_backend | return UnavailableBackend(tcfg, "dummy TTS is disabled") |
| 462 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_build_backend | if _dummy_allowed(cfg): |
| 463 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_build_backend | logger.warning("TTS unavailable (%s); explicit test dummy enabled", reason) |
| 464 | dummy | expected_test_or_preview | code_or_text | FunctionDef:_build_backend | return DummyBackend(tcfg) |
| 495 | fallback | review | code_or_text | FunctionDef:_resolve_piper_voice | language = normalize_lang(explicit, fallback=str(cfg.get("language", "tr"))) |

Direct import callers:

| from_path | import_module | import_name | line |
| --- | --- | --- | --- |
| modules/speak/xSpeakService.py | modules.speak.services.tts | TextToSpeech | 21 |
| modules/speak/xSpeakService.py | modules.speak.services.tts | TTSUnavailableError | 21 |
| modules/speak/xSpeakService.py | modules.speak.services.tts | cancel_synthesis | 115 |
| modules/speak/xSpeakService.py | modules.speak.services.tts | clear_synthesis_cancel | 161 |

Text references:

| from_path | line | key | snippet |
| --- | --- | --- | --- |
| config/agent.yaml | 249 | tts | 0248:     dtype: float32<br>0249:   tts:<br>0250:     engine: piper |
| config/agent.yaml | 259 | tts | 0258:       enabled: false<br>0259:       endpoint: http://192.168.1.100:5000/tts/synthesize<br>0260:       timeout: 120 |
| config/agent.yaml | 261 | tts | 0260:       timeout: 120<br>0261:       auth_token: sb-tts-AtG6w3BNcztOFF64tmXh-Wyi2cksngPO<br>0262:     piper: |
| config/agent.yaml | 293 | tts | 0292:       - tr<br>0293:     xtts:<br>0294:       endpoint: http://192.168.1.100:5000/tts/synthesize |
| config/agent.yaml | 294 | tts | 0293:     xtts:<br>0294:       endpoint: http://192.168.1.100:5000/tts/synthesize<br>0295:       timeout: 120 |
| modules/admin_ui/api/router.py | 188 | tts | 0187:         if isinstance(profile, dict):<br>0188:             speak_chunk = profile.get("speak_max_chunk_chars") or profile.get("tts_max_chunk_chars")<br>0189:  |
| modules/agent_core/services/action_arbiter.py | 67 | tts | 0066: _EXCLUSIVE_GROUPS: Dict[str, str] = {<br>0067:     "speak": "tts",<br>0068:     "vision_vlm_call": "vlm", |
| modules/agent_core/services/agent.py | 173 | tts | 0172:         if self.autonomy_client and hasattr(self.autonomy_client, "set_stt_suppressed"):<br>0173:             self.speech_arbiter.set_tts_state_callback(lambda active: self.autonomy_client.set_stt_suppressed(bool(active)))<br>0174:         if self.autonomy_client and hasattr(self.autonomy_client, "stop_speaking"): |
| modules/agent_core/services/agent.py | 509 | tts | 0508:         # Check speak remote auth_token. The current config stores it under<br>0509:         # speak.tts.remote.auth_token; older configs may also use speak.remote.<br>0510:         speak_cfg = config.get("speak", {}) if isinstance(config.get("speak", {}), dict) else {} |
| modules/agent_core/services/agent.py | 512 | tts | 0511:         remote_speak = speak_cfg.get("remote", {}) if isinstance(speak_cfg.get("remote", {}), dict) else {}<br>0512:         tts_cfg = speak_cfg.get("tts", {}) if isinstance(speak_cfg.get("tts", {}), dict) else {}<br>0513:         tts_remote = tts_cfg.get("remote", {}) if isinstance(tts_cfg.get("remote", {}), dict) else {} |
| modules/agent_core/services/agent.py | 513 | tts | 0512:         tts_cfg = speak_cfg.get("tts", {}) if isinstance(speak_cfg.get("tts", {}), dict) else {}<br>0513:         tts_remote = tts_cfg.get("remote", {}) if isinstance(tts_cfg.get("remote", {}), dict) else {}<br>0514:         speak_auth = str(remote_speak.get("auth_token", "") or tts_remote.get("auth_token", "") or "").strip() |
| modules/agent_core/services/agent.py | 514 | tts | 0513:         tts_remote = tts_cfg.get("remote", {}) if isinstance(tts_cfg.get("remote", {}), dict) else {}<br>0514:         speak_auth = str(remote_speak.get("auth_token", "") or tts_remote.get("auth_token", "") or "").strip()<br>0515:         if speak_auth in ("", "changeme", "your-auth-token", "replace_me"): |
| modules/agent_core/services/agent.py | 516 | tts | 0515:         if speak_auth in ("", "changeme", "your-auth-token", "replace_me"):<br>0516:             warnings.append("SECURITY WARNING: speak.tts.remote.auth_token is using default/empty value - please set a strong token in config/agent.yaml")<br>0517:          |
| modules/agent_core/services/speech_arbiter.py | 80 | tts | 0079:         self._current_item: Optional[SpeechItem] = None<br>0080:         self._tts_state_callback: Optional[Callable[[bool], Any]] = None<br>0081:         self._stop_playback_fn: Optional[Callable[[], Any]] = None |
| modules/agent_core/services/speech_arbiter.py | 84 | tts | 0083:         self._dedup_window_s = 5.0<br>0084:         self.tts_active = threading.Event()<br>0085:  |
| modules/agent_core/services/speech_arbiter.py | 102 | tts | 0101: <br>0102:     def set_tts_state_callback(self, fn: Callable[[bool], Any]) -> None:<br>0103:         self._tts_state_callback = fn |
| modules/agent_core/services/speech_arbiter.py | 103 | tts | 0102:     def set_tts_state_callback(self, fn: Callable[[bool], Any]) -> None:<br>0103:         self._tts_state_callback = fn<br>0104:  |
| modules/agent_core/services/speech_arbiter.py | 116 | tts | 0115:                 logger.debug("stop playback failed", exc_info=True)<br>0116:         self._set_tts_active(False)<br>0117:         with self._lock: |
| modules/agent_core/services/speech_arbiter.py | 249 | tts | 0248:     def is_speaking(self) -> bool:<br>0249:         return self.tts_active.is_set()<br>0250:  |
| modules/agent_core/services/speech_arbiter.py | 259 | tts | 0258:             return {<br>0259:                 "speaking": self.tts_active.is_set(),<br>0260:                 "queue_size": len(self._queue), |

## Compatibility / Degraded Path Reviews

| path | terms | severities | callers |
| --- | --- | --- | --- |
| modules/agent_core/services/agent.py | fallback | {"review": 42, "expected_degraded_path": 2} | 31 |
| modules/agent_core/services/memory.py | fallback | {"expected_degraded_path": 1} | 30 |
| modules/agent_core/services/progress.py | fallback | {"review": 2, "expected_degraded_path": 1} | 30 |
| modules/agent_core/services/tri_layer.py | fallback | {"review": 1, "expected_degraded_path": 1} | 29 |
| modules/arduino_serial/xArduinoSerialService.py | fallback | {"expected_degraded_path": 1, "review": 6} | 31 |
| modules/autonomy/services/brain_parts/responses.py | fallback, legacy | {"compatibility_review": 6, "review": 1} | 12 |
| modules/autonomy/services/client.py | fallback, legacy | {"compatibility_review": 1, "review": 3} | 30 |
| modules/autonomy/services/companion_goal_executor.py | noop | {"expected_degraded_path": 15} | 2 |
| modules/autonomy/services/recall.py | fallback | {"expected_degraded_path": 1, "review": 1} | 26 |
| modules/autonomy/services/relationship_memory.py | fallback | {"expected_degraded_path": 1} | 10 |
| modules/camera/config_loader.py | fallback | {"expected_degraded_path": 1} | 34 |
| modules/gateway/services/bootstrap.py | deprecated, fallback | {"compatibility_review": 1, "expected_degraded_path": 1} | 32 |
| modules/hardware/services/system.py | fallback | {"expected_degraded_path": 1} | 30 |
| modules/interactions/services/adapters/neopixel_client.py | noop | {"expected_degraded_path": 2} | 1 |
| modules/neopixel/services/companion_leds.py | fallback, legacy | {"compatibility_review": 1, "review": 2} | 6 |
| modules/neopixel/services/driver.py | fallback | {"expected_degraded_path": 1} | 32 |
| modules/oled_faces/services/face_renderer.py | legacy | {"compatibility_review": 1} | 2 |
| modules/oled_faces/services/legacy_map.py | legacy | {"compatibility_review": 8} | 7 |
| modules/oled_faces/services/mapper.py | fallback, legacy | {"compatibility_review": 1, "review": 6} | 19 |
| modules/oled_faces/xOledFacesService.py | legacy | {"compatibility_review": 1} | 13 |
| modules/ollama/api/router.py | fallback | {"expected_degraded_path": 1, "review": 2} | 34 |
| modules/ollama/services/translator.py | fallback | {"expected_degraded_path": 1, "review": 6} | 14 |
| modules/piservo/services/driver.py | fallback, no-op | {"expected_test_or_preview": 1, "expected_degraded_path": 1} | 31 |
| modules/runtime_console/config_loader.py | fallback | {"expected_degraded_path": 1} | 32 |
| modules/runtime_console/tui_v2.py | dummy, fallback | {"expected_degraded_path": 4, "expected_test_or_preview": 2} | 6 |
| modules/speak/services/lang_detect.py | fallback | {"expected_degraded_path": 1, "review": 7} | 10 |
| modules/vlm_bridge/services/llm_client.py | legacy | {"compatibility_review": 5} | 25 |
| modules/vlm_bridge/services/processor.py | legacy | {"compatibility_review": 6} | 32 |
| modules/wakeword/services/openwakeword_runner.py | fallback | {"expected_degraded_path": 1} | 4 |

## Config Records

| path | terms | severities |
| --- | --- | --- |
| config/agent.yaml | dummy, fallback | {"config_review": 23} |
| config/robot_capability_registry.json | fallback, noop | {"config_review": 4} |

## Documentation Records

| path | terms | severities |
| --- | --- | --- |
| modules/agent_core/MIGRATION_TRI_LAYER.md | fallback, legacy | {"documentation": 2} |
| modules/agent_core/README.md | fallback, legacy | {"documentation": 2} |
| modules/arduino_serial/architecture_arduino_serial.md | fallback | {"documentation": 2} |
| modules/arduino_serial/README.md | fake, fallback, legacy | {"documentation": 5} |
| modules/autonomy/architecture_autonomy.md | fallback | {"documentation": 1} |
| modules/autonomy/README.md | fallback | {"documentation": 5} |
| modules/common/README.md | fallback | {"documentation": 1} |
| modules/diagnostics/architecture_diagnostics.md | fallback | {"documentation": 1} |
| modules/interactions/README.md | no-op | {"documentation": 1} |
| modules/mutagen/README.md | no-op | {"documentation": 1} |
| modules/neopixel/architecture_neopixel.md | dummy | {"documentation": 1} |
| modules/oled_faces/architecture_oled_faces.md | legacy | {"documentation": 3} |
| modules/oled_faces/config/README.md | fallback, legacy | {"documentation": 2} |
| modules/oled_faces/README.md | legacy | {"documentation": 1} |
| modules/ollama/architecture_ollama.md | fallback | {"documentation": 3} |
| modules/piservo/architecture_piservo.md | mock | {"documentation": 4} |
| modules/runtime_console/README.md | fallback | {"documentation": 1} |
| modules/speak/architecture_speak.md | fallback | {"documentation": 1} |
| modules/speak/config/README.md | dummy | {"documentation": 1} |
| modules/speak/README.md | dummy | {"documentation": 1} |
| services/remote_multimodal_server/README.md | fallback, legacy | {"documentation": 4} |

## Recommended Next

- Do not delete stub/legacy files without caller analysis.
- If a candidate has callers, replace through an adapter or update callers first.
- If a candidate has zero callers and no dynamic gateway usage, mark for cleanup after CI guard.
- Keep degraded/fallback paths when they represent safe robot behavior with missing optional hardware.
- Next patch should target only one confirmed candidate at a time.
