from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import requests

from modules.ai_provider.models.sentry_schema import SentryResponse
from modules.ai_provider.services.clients import CircuitOpenError
from modules.ai_provider.services.google_ai_client import ProviderDisabledError
from modules.common.url_utils import resolve_config_url

logger = logging.getLogger("ollama.api")
_HTTP_SESSION = requests.Session()


def _safe_llm_exc_text(exc: Exception) -> str:
    try:
        from modules.common.config_loader import redact_secrets

        return redact_secrets(str(exc))[:500]
    except Exception:
        return str(exc)[:500]


def _is_llm_not_found(exc: Exception) -> bool:
    msg = _safe_llm_exc_text(exc).lower()
    return (
        "404" in msg
        or "not found" in msg
        or "model not found" in msg
        or "status code: 404" in msg
    )


def _llm_unavailable_payload(
    *,
    provider_name: str,
    model: str,
    active_persona: str,
    detail: str,
    reason: str = "llm_model_unavailable",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "answer": "",
        "text": "",
        "thoughts": "",
        "persona": active_persona,
        "model": model,
        "provider": provider_name,
        "error": reason,
        "reason": reason,
        "detail": detail,
    }


def _post_action_json(url: str, payload: Dict[str, Any], timeout: float) -> None:
    post_fn = getattr(requests, "post", None)
    if getattr(post_fn, "__module__", "") == "requests.api":
        _HTTP_SESSION.post(url, json=payload, timeout=timeout)
    else:
        requests.post(url, json=payload, timeout=timeout)


def get_chat_router(
    chat: Any,
    translator: Any,
    model: str,
    provider_name: str,
    active_persona: str,
    action_endpoint: str,
    action_timeout: float,
    default_apply: bool,
    *,
    runtime: Optional[Dict[str, Any]] = None,
) -> APIRouter:
    r = APIRouter(tags=["ollama-chat"])
    resolved_action_endpoint = resolve_config_url(action_endpoint) if action_endpoint else ""

    def _active_context() -> tuple[Any, str, str]:
        if runtime is None:
            return chat, model, active_persona
        lock = runtime.get("_lock")
        if lock is not None:
            with lock:
                return (
                    runtime.get("chat") or chat,
                    str(runtime.get("model") or model),
                    str(runtime.get("active_persona") or active_persona),
                )
        return (
            runtime.get("chat") or chat,
            str(runtime.get("model") or model),
            str(runtime.get("active_persona") or active_persona),
        )

    def _format_chat_payload(
        result: Dict[str, Any],
        cur_model: str,
        cur_persona: str,
        translation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": True,
            "answer": result.get("text", ""),
            "text": result.get("text", ""),
            "thoughts": result.get("thoughts", ""),
            "persona": cur_persona,
            "model": cur_model,
            "provider": provider_name,
        }
        if result.get("actions"):
            payload["actions"] = result["actions"]
        if "raw" in result:
            payload["raw"] = result.get("raw")
        if translation:
            payload["translation"] = translation
        return payload

    def _maybe_dispatch_actions(result: Dict[str, Any], apply_flag: bool) -> None:
        if not apply_flag or not resolved_action_endpoint:
            return
        actions = result.get("actions")
        if not actions:
            return
        payload = {
            "text": result.get("text", ""),
            "raw": result.get("raw"),
            "actions": actions,
            "speak": False,
        }
        try:
            _post_action_json(resolved_action_endpoint, payload, timeout=action_timeout)
        except Exception as exc:
            logger.warning("Failed to dispatch persona actions: %s", exc)

    def _prepare_translation(
        query: str,
        source_lang: Optional[str],
        response_lang: Optional[str],
    ) -> tuple[str, str, str, bool]:
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        auto_detected = False
        if source == "auto":
            source = translator.detect_language(query)
            auto_detected = True
        target = translator.normalize_lang(response_lang or source, fallback=translator.cfg.default_source_lang)
        query_en = translator.to_bridge(query, source)
        return source, target, query_en, auto_detected

    def _resolve_requested_model(
        role: Optional[str],
        model: Optional[str],
        cur_model: str,
    ) -> Optional[str]:
        requested_model = str(model or "").strip()
        requested_role = str(role or "").strip().lower()
        if not requested_model and not requested_role:
            return None
        rt_cfg = runtime.get("cfg") if isinstance(runtime, dict) and isinstance(runtime.get("cfg"), dict) else {}
        if not requested_model and requested_role:
            from modules.common.model_roles import resolve_role_model

            requested_model = resolve_role_model(rt_cfg, requested_role, fallback=cur_model)
        if not requested_model or requested_model == cur_model:
            return None
        llm_section = rt_cfg.get("llm", {}) if isinstance(rt_cfg.get("llm"), dict) else {}
        if llm_section.get("single_model_mode") is True:
            return None
        raw_allowed = llm_section.get("allowed_models")
        if isinstance(raw_allowed, (list, tuple, set)):
            allowed = {str(x).strip() for x in raw_allowed if str(x).strip()}
            if allowed and requested_model not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Requested model '{requested_model}' is not in allowed_models",
                )
        return requested_model

    def _chat_stream_response(
        query: str,
        apply_actions: Optional[bool],
        structured: bool,
        source_lang: Optional[str],
        response_lang: Optional[str],
        role: Optional[str] = None,
        model: Optional[str] = None,
    ) -> StreamingResponse:
        active_chat, cur_model, cur_persona = _active_context()
        override_model = _resolve_requested_model(role, model, cur_model)
        effective_model = override_model or cur_model
        source, target, query_en, auto_detected = _prepare_translation(query, source_lang, response_lang)
        response_format = SentryResponse.model_json_schema() if structured else None
        flag = default_apply if apply_actions is None else apply_actions

        def _event_gen() -> Iterator[str]:
            stream_fn = getattr(active_chat, "chat_stream", None)
            try:
                stream_kwargs: Dict[str, Any] = {"response_format": response_format}
                if override_model:
                    stream_kwargs["model"] = override_model
                if callable(stream_fn):
                    iterator = stream_fn(query_en, **stream_kwargs)
                else:
                    chat_kwargs: Dict[str, Any] = {}
                    if response_format is not None:
                        chat_kwargs["response_format"] = response_format
                    if override_model:
                        chat_kwargs["model"] = override_model
                    res = active_chat.chat(query_en, **chat_kwargs)
                    iterator = iter([{"type": "done", "result": res}])

                for evt in iterator:
                    if evt.get("type") == "delta":
                        line = json.dumps({"delta": evt.get("delta", ""), "done": bool(evt.get("done", False))}, ensure_ascii=False)
                        yield f"data: {line}\n\n"
                    elif evt.get("type") == "done":
                        result = dict(evt.get("result") or {})
                        answer_en = str(result.get("text", ""))
                        localized = translator.from_bridge(answer_en, target)
                        result["text"] = localized
                        _maybe_dispatch_actions(result, flag)
                        translation_meta = {
                            "enabled": bool(translator.cfg.enabled),
                            "request_lang": source,
                            "bridge_lang": translator.BRIDGE_LANG,
                            "response_lang": target,
                            "query_bridge": query_en,
                            "answer_bridge": answer_en,
                            "auto_detected": auto_detected,
                        }
                        final_payload = _format_chat_payload(result, effective_model, cur_persona, translation=translation_meta)
                        final_payload["done"] = True
                        yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"
            except CircuitOpenError as exc:
                err = _llm_unavailable_payload(
                    provider_name=provider_name,
                    model=effective_model,
                    active_persona=cur_persona,
                    detail=_safe_llm_exc_text(exc),
                    reason="circuit_breaker_open",
                )
                yield f"data: {json.dumps({**err, 'done': True}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                err = _llm_unavailable_payload(
                    provider_name=provider_name,
                    model=effective_model,
                    active_persona=cur_persona,
                    detail=_safe_llm_exc_text(exc),
                    reason="llm_stream_failed",
                )
                yield f"data: {json.dumps({**err, 'done': True}, ensure_ascii=False)}\n\n"

        return StreamingResponse(_event_gen(), media_type="text/event-stream")

    def _chat_response(
        query: str,
        apply_actions: Optional[bool],
        source_lang: Optional[str],
        response_lang: Optional[str],
        structured: bool = False,
        role: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        active_chat, cur_model, cur_persona = _active_context()
        override_model = _resolve_requested_model(role, model, cur_model)
        effective_model = override_model or cur_model
        source, target, query_en, auto_detected = _prepare_translation(query, source_lang, response_lang)
        response_format = SentryResponse.model_json_schema() if structured else None

        try:
            chat_kwargs: Dict[str, Any] = {}
            if response_format is not None:
                chat_kwargs["response_format"] = response_format
            if override_model:
                chat_kwargs["model"] = override_model
            result = active_chat.chat(query_en, **chat_kwargs)
        except ProviderDisabledError as exc:
            return _llm_unavailable_payload(
                provider_name=provider_name,
                model=cur_model,
                active_persona=cur_persona,
                detail=_safe_llm_exc_text(exc),
                reason="provider_disabled",
            )
        except CircuitOpenError as exc:
            return _llm_unavailable_payload(
                provider_name=provider_name,
                model=cur_model,
                active_persona=cur_persona,
                detail=_safe_llm_exc_text(exc),
                reason="circuit_breaker_open",
            )
        except requests.HTTPError as exc:
            detail = _safe_llm_exc_text(exc)
            if _is_llm_not_found(exc):
                logger.info("LLM chat unavailable; using fallback path: %s", detail)
                return _llm_unavailable_payload(
                    provider_name=provider_name,
                    model=cur_model,
                    active_persona=cur_persona,
                    detail=detail,
                )
            logger.warning("LLM upstream request failed: %s", detail)
            raise HTTPException(status_code=502, detail="LLM upstream request failed") from exc
        except Exception as exc:
            detail = _safe_llm_exc_text(exc)
            if _is_llm_not_found(exc):
                logger.info("LLM chat unavailable; using fallback path: %s", detail)
                return _llm_unavailable_payload(
                    provider_name=provider_name,
                    model=cur_model,
                    active_persona=cur_persona,
                    detail=detail,
                )
            logger.exception("LLM chat failed: %s", detail)
            raise HTTPException(status_code=500, detail="LLM chat failed") from exc

        answer_en = str(result.get("text", ""))
        localized_answer = translator.from_bridge(answer_en, target)
        result["text"] = localized_answer

        flag = default_apply if apply_actions is None else apply_actions
        _maybe_dispatch_actions(result, flag)

        translation_meta = {
            "enabled": bool(translator.cfg.enabled),
            "request_lang": source,
            "bridge_lang": translator.BRIDGE_LANG,
            "response_lang": target,
            "query_bridge": query_en,
            "answer_bridge": answer_en,
            "auto_detected": auto_detected,
        }
        return _format_chat_payload(result, effective_model, cur_persona, translation=translation_meta)

    @r.get("/chat")
    def chat_get(
        query: str = Query(...),
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        stream: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
        role: Optional[str] = None,
        model: Optional[str] = None,
    ):
        if stream:
            return _chat_stream_response(
                query,
                apply_actions,
                structured,
                source_lang,
                response_lang,
                role=role,
                model=model,
            )
        return _chat_response(
            query,
            apply_actions,
            source_lang,
            response_lang,
            structured=structured,
            role=role,
            model=model,
        )

    @r.post("/chat")
    def chat_post(
        query: str,
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        stream: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
        role: Optional[str] = None,
        model: Optional[str] = None,
    ):
        if stream:
            return _chat_stream_response(
                query,
                apply_actions,
                structured,
                source_lang,
                response_lang,
                role=role,
                model=model,
            )
        return _chat_response(
            query,
            apply_actions,
            source_lang,
            response_lang,
            structured=structured,
            role=role,
            model=model,
        )

    @r.post("/translate")
    def translate(text: str, source_lang: str = "auto", target_lang: str = "en"):
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        target = translator.normalize_lang(target_lang, fallback=translator.BRIDGE_LANG)
        if source_lang == "auto":
            source = translator.detect_language(text)
        out = translator.translate(text, source, target)
        return {"ok": True, "text": out, "source_lang": source, "target_lang": target}

    @r.post("/runtime/num_predict")
    def runtime_num_predict(body: Dict[str, Any]):
        np_raw = body.get("num_predict")
        if np_raw is None:
            raise HTTPException(status_code=400, detail="num_predict required")
        try:
            np_val = max(48, int(np_raw))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid num_predict: {exc}") from exc
        active_chat, _, _ = _active_context()
        if hasattr(active_chat, "set_num_predict"):
            actual = active_chat.set_num_predict(np_val)
        else:
            active_chat.num_predict = np_val
            actual = int(active_chat.num_predict)
        return {"ok": True, "num_predict": actual}

    return r
