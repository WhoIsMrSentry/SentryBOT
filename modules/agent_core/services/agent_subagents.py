from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .tri_layer import SubAgentProfile

logger = logging.getLogger("agent.orchestrator")


class AgentSubagentsMixin:
    """Sub-agent task delegation and persona synthesis for AgentOrchestrator."""

    subagent_profiles: Dict[str, Any]
    subagent_workers: int
    persona_system_prompt: str
    persona_num_predict: int
    persona_stream_enabled: bool
    temperature: float
    num_ctx: int
    last_routed_subagents: List[str]
    router: Any
    _chat_turn: Callable[..., Any]
    _chat_maybe_stream: Callable[..., Any]
    _stream_turn_sentence_by_sentence: Callable[..., Any]

    def _route_subagents(self, prompt: str) -> List[SubAgentProfile]:
        low = prompt.lower()
        selected: List[SubAgentProfile] = []

        for name, profile in self.subagent_profiles.items():
            if not profile.enabled:
                continue
            matches = any(k in low for k in profile.keywords)
            if matches:
                selected.append(profile)

        if not selected and "fast_reflex" in self.subagent_profiles:
            reflex = self.subagent_profiles["fast_reflex"]
            if reflex.enabled:
                selected.append(reflex)

        return selected

    def _run_subagent_task(self, profile: SubAgentProfile, sub_prompt: str) -> Dict[str, Any]:
        t0 = time.time()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": profile.system_prompt},
            {"role": "user", "content": sub_prompt},
        ]
        options: Dict[str, Any] = {
            "temperature": profile.temperature,
            "num_predict": profile.num_predict,
        }
        res = self._chat_turn(profile.model, messages, tools=None, options=options)
        text = res.get("message", {}).get("content", "")
        return {
            "name": profile.name,
            "text": text,
            "duration_ms": int((time.time() - t0) * 1000),
            "actions": [],
        }

    def _summarize_actions(self, subagent_reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for r in subagent_reports:
            for act in r.get("actions", []):
                actions.append(act)
        return actions

    def _run_tri_layer(
        self,
        user_prompt: str,
        world_context: str,
        survival_override: Optional[str],
        active_model: str,
        session_language: str,
        progress_token: str,
        callback: Optional[Callable],
        on_sentence: Optional[Callable[[str, int], None]] = None,
    ) -> Tuple[str, int, List[Dict[str, Any]]]:
        profiles = self._route_subagents(user_prompt)
        self.last_routed_subagents = [p.name for p in profiles]
        subagent_reports: List[Dict[str, Any]] = []

        if profiles:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.subagent_workers) as executor:
                fut_map = {executor.submit(self._run_subagent_task, p, user_prompt): p for p in profiles}
                for fut in concurrent.futures.as_completed(fut_map):
                    try:
                        subagent_reports.append(fut.result())
                    except Exception as e:
                        logger.error("Subagent execution failed: %s", e)

        synth_res = self._synthesize_persona_response(user_prompt, subagent_reports, on_sentence=on_sentence)
        final_text = synth_res.get("message", {}).get("content", "")
        return final_text, len(subagent_reports), subagent_reports

    def _synthesize_persona_response(
        self,
        user_prompt: str,
        subagent_results: List[Dict[str, Any]],
        on_sentence: Optional[Callable[..., None]] = None,
    ) -> Dict[str, Any]:
        combined_context: List[str] = []
        for r in subagent_results:
            combined_context.append(f"[{r.get('name', 'subagent')}]: {r.get('text', '')}")

        context_str = "\n\n".join(combined_context)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.persona_system_prompt},
            {
                "role": "user",
                "content": f"USER PROMPT: {user_prompt}\n\nSPECIALIST FINDINGS:\n{context_str}\n\nRespond to the user naturally in character.",
            },
        ]
        options: Dict[str, Any] = {
            "temperature": self.temperature,
            "num_predict": self.persona_num_predict,
            "num_ctx": self.num_ctx,
        }

        default_model = getattr(self, "default_model", "qwen3.5:9b")
        if self.persona_stream_enabled and on_sentence:
            return self._stream_turn_sentence_by_sentence(
                default_model, messages, tools=None, options=options, on_sentence=on_sentence
            )
        return self._chat_turn(default_model, messages, tools=None, options=options)
