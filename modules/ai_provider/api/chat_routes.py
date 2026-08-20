from __future__ import annotations
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
import requests

logger = logging.getLogger("ollama.api")


def _safe_llm_exc_text(exc: Exception) -> str:
    try:
        from modules.system_control.config_center.log_redact import redact_secrets

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


def get_chat_router(
    chat: Any,
    translator: Any,
    model: str,
    provider_name: str,
    active_persona: str,
    action_endpoint: str,
    action_timeout: float,
    default_apply: bool,
) -> APIRouter:
    r = APIRouter(tags=["ollama-chat"])

    def _format_chat_payload(result: Dict[str, Any], translation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": True,
            "answer": result.get("text", ""),
            "text": result.get("text", ""),
            "thoughts": result.get("thoughts", ""),
            "persona": active_persona,
            "model": model,
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
        if not apply_flag or not action_endpoint:
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
            requests.post(action_endpoint, json=payload, timeout=action_timeout)
        except Exception as exc:
            logger.warning("Failed to dispatch persona actions: %s", exc)

    def _chat_response(
        query: str,
        apply_actions: Optional[bool],
        source_lang: Optional[str],
        response_lang: Optional[str],
    ) -> Dict[str, Any]:
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        if source == "auto":
            source = translator.detect_language(query)
        target = translator.normalize_lang(response_lang or source, fallback=translator.cfg.default_source_lang)
        query_en = translator.to_bridge(query, source)

        try:
            result = chat.chat(query_en)
        except requests.HTTPError as exc:
            detail = _safe_llm_exc_text(exc)
            if _is_llm_not_found(exc):
                logger.info("LLM chat unavailable; using fallback path: %s", detail)
                return _llm_unavailable_payload(
                    provider_name=provider_name,
                    model=model,
                    active_persona=active_persona,
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
                    model=model,
                    active_persona=active_persona,
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
            "auto_detected": bool(source_lang and str(source_lang).strip().lower() == "auto"),
        }
        return _format_chat_payload(result, translation=translation_meta)

    @r.get("/chat")
    def chat_get(
        query: str = Query(...),
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
    ):
        return _chat_response(query, apply_actions, source_lang, response_lang)

    @r.post("/chat")
    def chat_post(
        query: str,
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
    ):
        return _chat_response(query, apply_actions, source_lang, response_lang)

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
        chat.num_predict = np_val
        return {"ok": True, "num_predict": chat.num_predict}

    return r
