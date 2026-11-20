"""Hybrid Neural Machine Translation (online Google + offline local NMT fallback).

Provides fast, non-LLM translation for SentryBOT so Turkish/non-English speech
can be translated to English for stronger LLM reasoning and translated back
for natural TTS output without spinning up a second Ollama LLM.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("common.translator")

try:
    from langdetect import DetectorFactory, detect as _detect_lang  # type: ignore

    DetectorFactory.seed = 0
except Exception:
    _detect_lang = None  # type: ignore

try:
    from modules.voice.speak.services.lang_detect import detect_text_language as _heuristic_detect_lang
except Exception:
    _heuristic_detect_lang = None  # type: ignore

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_TR_HINT_WORDS = frozenset({
    "merhaba", "naber", "evet", "hayir", "hayır", "tamam", "günaydın", "gunaydin",
    "nasilsin", "nasılsın", "iyi", "degil", "değil", "lutfen", "lütfen",
    "selam", "nedir", "neden", "kim", "nasıl", "nerede", "sinirlen", "teşekkürler",
})
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…\n])\s+")
_VALID_MODES = frozenset({"online_first", "hybrid", "local_first", "local_only", "online_only", "ollama"})
_GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


@dataclass
class HybridTranslatorConfig:
    enabled: bool = True
    mode: str = "online_first"
    default_source_lang: str = "tr"
    bridge_lang: str = "en"
    local_models_dir: str = "models/translate"
    online_timeout_s: float = 2.5
    online_cooldown_s: float = 15.0
    cache_size: int = 256
    local_threads: int = 2
    allow_hf_download: bool = False
    fallback_to_ollama: bool = False
    ollama_model: Optional[str] = None

    @property
    def model(self) -> Optional[str]:
        return self.ollama_model

    @model.setter
    def model(self, value: Optional[str]) -> None:
        self.ollama_model = value

    @classmethod
    def from_dict(cls, cfg: Optional[Dict[str, Any]]) -> "HybridTranslatorConfig":
        raw = cfg if isinstance(cfg, dict) else {}
        mode = str(raw.get("mode", raw.get("backend", "online_first")) or "online_first").strip().lower()
        if mode not in _VALID_MODES:
            mode = "online_first"
        return cls(
            enabled=bool(raw.get("enabled", True)),
            mode=mode,
            default_source_lang=str(raw.get("default_source_lang", "tr") or "tr").strip().lower(),
            bridge_lang=str(raw.get("bridge_lang", "en") or "en").strip().lower(),
            local_models_dir=str(raw.get("local_models_dir", "models/translate") or "models/translate").strip(),
            online_timeout_s=max(0.4, float(raw.get("online_timeout_s", 2.5) or 2.5)),
            online_cooldown_s=max(1.0, float(raw.get("online_cooldown_s", 15.0) or 15.0)),
            cache_size=max(0, int(raw.get("cache_size", 256) or 0)),
            local_threads=max(1, int(raw.get("local_threads", 2) or 2)),
            allow_hf_download=bool(raw.get("allow_hf_download", False)),
            fallback_to_ollama=bool(raw.get("fallback_to_ollama", False)),
            ollama_model=str(raw.get("model", "") or "").strip() or None,
        )


def split_translation_chunks(text: str, max_chars: int = 1000) -> List[str]:
    """Split long text on sentence boundaries without breaking short lines."""
    raw = str(text or "").strip()
    if not raw or len(raw) <= max_chars:
        return [raw] if raw else []
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for part in _SENTENCE_SPLIT_RE.split(raw):
        piece = part.strip()
        if not piece:
            continue
        if cur and cur_len + len(piece) + 1 > max_chars:
            chunks.append(" ".join(cur))
            cur = [piece]
            cur_len = len(piece)
        else:
            cur.append(piece)
            cur_len += len(piece) + 1
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def _parse_google_response(payload: Any) -> str:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        return ""
    parts: List[str] = []
    for seg in payload[0]:
        if isinstance(seg, list) and seg and isinstance(seg[0], str):
            parts.append(seg[0])
    return "".join(parts).strip()


class _GoogleOnlineBackend:
    """Zero-dependency HTTP translator backed by Google Translate endpoint."""

    def __init__(self, timeout_s: float = 2.5, cooldown_s: float = 15.0) -> None:
        self.timeout_s = float(timeout_s)
        self.cooldown_s = float(cooldown_s)
        self._offline_until = 0.0
        self._lock = threading.Lock()
        self._session: Any = None

    def _get_session(self) -> Any:
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def in_cooldown(self) -> bool:
        with self._lock:
            return time.monotonic() < self._offline_until

    def mark_offline(self) -> None:
        with self._lock:
            self._offline_until = time.monotonic() + self.cooldown_s

    def clear_offline(self) -> None:
        with self._lock:
            self._offline_until = 0.0

    def translate(self, text: str, src: str, tgt: str) -> Optional[str]:
        if self.in_cooldown():
            return None
        chunks = split_translation_chunks(text, max_chars=900)
        if not chunks:
            return ""
        sess = self._get_session()
        out_parts: List[str] = []
        try:
            for chunk in chunks:
                resp = sess.get(
                    _GOOGLE_ENDPOINT,
                    params={"client": "gtx", "sl": src, "tl": tgt, "dt": "t", "q": chunk},
                    timeout=self.timeout_s,
                )
                if resp.status_code != 200:
                    self.mark_offline()
                    return None
                parsed = _parse_google_response(resp.json())
                if not parsed:
                    return None
                out_parts.append(parsed)
            self.clear_offline()
            return " ".join(out_parts).strip()
        except Exception as exc:
            self.mark_offline()
            logger.debug("Google online translation unavailable (%s->%s): %s", src, tgt, exc)
            return None


class _LocalNMTBackend:
    """Lazy offline NMT backend supporting CTranslate2, Argos Translate, and HF Opus-MT."""

    def __init__(self, models_dir: str, threads: int = 2, allow_hf_download: bool = False) -> None:
        self.models_dir = Path(models_dir)
        self.threads = max(1, int(threads))
        self.allow_hf_download = bool(allow_hf_download)
        self._lock = threading.Lock()
        self._ct2_cache: Dict[Tuple[str, str], Any] = {}
        self._hf_cache: Dict[Tuple[str, str], Any] = {}
        self._unavailable_pairs: Dict[Tuple[str, str], float] = {}

    def _pair_candidates(self, src: str, tgt: str) -> List[Path]:
        return [
            self.models_dir / f"{src}-{tgt}",
            self.models_dir / f"opus-mt-{src}-{tgt}",
            self.models_dir / f"opus-mt-tc-big-{src}-{tgt}",
        ]

    def _find_ct2_dir(self, src: str, tgt: str) -> Optional[Path]:
        for cand in self._pair_candidates(src, tgt):
            if (cand / "model.bin").is_file():
                return cand
        return None

    def _load_ct2_pair(self, src: str, tgt: str) -> Optional[Tuple[Any, Any, Any]]:
        key = (src, tgt)
        if key in self._ct2_cache:
            return self._ct2_cache[key]
        model_dir = self._find_ct2_dir(src, tgt)
        if model_dir is None:
            return None
        try:
            import ctranslate2  # type: ignore

            translator = ctranslate2.Translator(
                str(model_dir),
                device="cpu",
                compute_type="int8",
                inter_threads=1,
                intra_threads=self.threads,
            )
            src_tok, tgt_tok = self._load_ct2_tokenizers(model_dir)
            if src_tok is None or tgt_tok is None:
                return None
            bundle = (translator, src_tok, tgt_tok)
            self._ct2_cache[key] = bundle
            return bundle
        except Exception as exc:
            logger.debug("CTranslate2 load failed for %s->%s: %s", src, tgt, exc)
            return None

    @staticmethod
    def _load_ct2_tokenizers(model_dir: Path) -> Tuple[Any, Any]:
        src_spm = model_dir / "source.spm"
        tgt_spm = model_dir / "target.spm"
        if src_spm.is_file() and tgt_spm.is_file():
            try:
                import sentencepiece as spm  # type: ignore

                return (
                    ("spm", spm.SentencePieceProcessor(model_file=str(src_spm))),
                    ("spm", spm.SentencePieceProcessor(model_file=str(tgt_spm))),
                )
            except Exception:
                pass
        try:
            from transformers import AutoTokenizer  # type: ignore

            tok = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
            return ("hf", tok), ("hf", tok)
        except Exception:
            return None, None

    def _translate_ct2(self, text: str, src: str, tgt: str) -> Optional[str]:
        bundle = self._load_ct2_pair(src, tgt)
        if bundle is None:
            return None
        translator, src_tok, tgt_tok = bundle
        chunks = split_translation_chunks(text, max_chars=450)
        if not chunks:
            return ""
        try:
            tokenized: List[List[str]] = []
            for chunk in chunks:
                kind, tok = src_tok
                if kind == "spm":
                    tokens = tok.encode(chunk, out_type=str)
                else:
                    tokens = tok.convert_ids_to_tokens(tok.encode(chunk, truncation=True))
                tokenized.append(list(tokens))
            results = translator.translate_batch(tokenized, beam_size=2)
            decoded: List[str] = []
            kind_t, tok_t = tgt_tok
            for res in results:
                hyp = list(res.hypotheses[0]) if res.hypotheses else []
                if kind_t == "spm":
                    decoded.append(str(tok_t.decode(hyp)).strip())
                else:
                    ids = tok_t.convert_tokens_to_ids(hyp)
                    decoded.append(str(tok_t.decode(ids, skip_special_tokens=True)).strip())
            out = " ".join(p for p in decoded if p).strip()
            return out or None
        except Exception as exc:
            logger.debug("CTranslate2 inference failed (%s->%s): %s", src, tgt, exc)
            return None

    @staticmethod
    def _translate_argos(text: str, src: str, tgt: str) -> Optional[str]:
        try:
            import argostranslate.translate as argos_translate  # type: ignore

            out = argos_translate.translate(text, src, tgt)
            cleaned = str(out or "").strip()
            return cleaned or None
        except Exception:
            return None

    def _find_hf_dir_or_id(self, src: str, tgt: str) -> Optional[Tuple[str, bool]]:
        for cand in self._pair_candidates(src, tgt):
            if (cand / "config.json").is_file() and (
                (cand / "model.safetensors").is_file() or (cand / "pytorch_model.bin").is_file()
            ):
                return str(cand), True
        if self.allow_hf_download:
            return f"Helsinki-NLP/opus-mt-{src}-{tgt}", False
        return None

    def _load_hf_pair(self, src: str, tgt: str) -> Optional[Tuple[Any, Any]]:
        key = (src, tgt)
        if key in self._hf_cache:
            return self._hf_cache[key]
        resolved = self._find_hf_dir_or_id(src, tgt)
        if resolved is None:
            return None
        model_id, local_only = resolved
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # type: ignore

            tok = AutoTokenizer.from_pretrained(model_id, local_files_only=local_only)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_id, local_files_only=local_only)
            model.eval()
            bundle = (tok, model)
            self._hf_cache[key] = bundle
            return bundle
        except Exception as exc:
            logger.debug("HF local translation load skipped (%s->%s): %s", src, tgt, exc)
            return None

    def _translate_hf(self, text: str, src: str, tgt: str) -> Optional[str]:
        bundle = self._load_hf_pair(src, tgt)
        if bundle is None:
            return None
        tok, model = bundle
        chunks = split_translation_chunks(text, max_chars=450)
        if not chunks:
            return ""
        try:
            import torch  # type: ignore

            with torch.inference_mode():
                batch = tok(chunks, return_tensors="pt", padding=True, truncation=True, max_length=384)
                gen = model.generate(**batch, num_beams=2, max_new_tokens=256)
                out_parts = tok.batch_decode(gen, skip_special_tokens=True)
            out = " ".join(str(p).strip() for p in out_parts if str(p).strip()).strip()
            return out or None
        except Exception as exc:
            logger.debug("HF inference failed (%s->%s): %s", src, tgt, exc)
            return None

    def translate(self, text: str, src: str, tgt: str) -> Tuple[Optional[str], str]:
        with self._lock:
            out = self._translate_ct2(text, src, tgt)
            if out:
                return out, "local_ctranslate2"
            out = self._translate_argos(text, src, tgt)
            if out:
                return out, "local_argos"
            out = self._translate_hf(text, src, tgt)
            if out:
                return out, "local_transformers"
        return None, "unavailable"


class HybridTranslator:
    """Thread-safe translator using Google Translate online + local NMT offline fallback."""

    BRIDGE_LANG = "en"

    def __init__(
        self,
        cfg: Optional[Dict[str, Any]] = None,
        *,
        ollama_client: Any = None,
    ) -> None:
        self.cfg = HybridTranslatorConfig.from_dict(cfg)
        self.BRIDGE_LANG = self.cfg.bridge_lang or "en"
        self.ollama_client = ollama_client
        self._online = _GoogleOnlineBackend(
            timeout_s=self.cfg.online_timeout_s,
            cooldown_s=self.cfg.online_cooldown_s,
        )
        self._local = _LocalNMTBackend(
            models_dir=self.cfg.local_models_dir,
            threads=self.cfg.local_threads,
            allow_hf_download=self.cfg.allow_hf_download,
        )
        self._lock = threading.Lock()
        self._cache: "OrderedDict[Tuple[str, str, str], Tuple[str, str]]" = OrderedDict()
        self._detect_cache: "OrderedDict[str, str]" = OrderedDict()
        self._last_backend: str = "none"

    @staticmethod
    def normalize_lang(lang: Optional[str], fallback: str = "en") -> str:
        raw = (lang or "").strip().lower().replace("_", "-")
        if not raw:
            return fallback
        if "-" in raw:
            raw = raw.split("-", 1)[0]
        return raw

    def detect_language(self, text: str, default: Optional[str] = None) -> str:
        fallback = (
            self.normalize_lang(default, fallback=self.cfg.default_source_lang)
            if default
            else self.cfg.default_source_lang
        )
        value = str(text or "").strip()
        if not value:
            return fallback
        cache_key = f"{fallback}\x00{value}"
        cached = self._detect_cache_get(cache_key)
        if cached:
            return cached

        words = {w.strip(".,!?;:\"'()").lower() for w in value.split() if w.strip()}
        lang: Optional[str] = None
        if _heuristic_detect_lang is not None:
            guessed = _heuristic_detect_lang(value, default="__unknown__", prefer_online=False)
            if guessed in {"tr", "en"}:
                lang = guessed
        if lang is None and (any(ch in _TR_CHARS for ch in value) or (words & _TR_HINT_WORDS)):
            lang = "tr"
        if lang is None and _detect_lang is not None:
            try:
                detected = self.normalize_lang(str(_detect_lang(value)), fallback="")
                if detected and detected != "auto":
                    lang = detected
            except Exception as exc:
                logger.debug("langdetect failed, using default source language: %s", exc)
        if not lang:
            lang = fallback

        self._detect_cache_put(cache_key, lang)
        return lang

    def _cache_get(self, key: Tuple[str, str, str]) -> Optional[Tuple[str, str]]:
        if not self.cfg.cache_size:
            return None
        with self._lock:
            val = self._cache.get(key)
            if val is not None:
                self._cache.move_to_end(key)
            return val

    def _cache_put(self, key: Tuple[str, str, str], value: str, backend: str) -> None:
        if not self.cfg.cache_size:
            return
        with self._lock:
            self._cache[key] = (value, backend)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cfg.cache_size:
                self._cache.popitem(last=False)

    def _detect_cache_get(self, text: str) -> Optional[str]:
        if not self.cfg.cache_size:
            return None
        with self._lock:
            val = self._detect_cache.get(text)
            if val is not None:
                self._detect_cache.move_to_end(text)
            return val

    def _detect_cache_put(self, text: str, lang: str) -> None:
        if not self.cfg.cache_size:
            return
        with self._lock:
            self._detect_cache[text] = lang
            self._detect_cache.move_to_end(text)
            while len(self._detect_cache) > self.cfg.cache_size:
                self._detect_cache.popitem(last=False)

    def _translate_ollama(self, text: str, src: str, tgt: str) -> Optional[str]:
        if self.ollama_client is None or not hasattr(self.ollama_client, "chat"):
            return None
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a translation engine. "
                    "Return only translated text with no commentary, no markdown, no quotes. "
                    "Preserve intent, entities, and imperative tone."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Translate from {src} to {tgt}.\n"
                    "If text is already in target language, return it unchanged.\n"
                    f"Text: {text}"
                ),
            },
        ]
        try:
            resp = self.ollama_client.chat(
                messages,
                options={"temperature": 0.0},
                model=self.cfg.ollama_model,
            )
            translated = str((resp or {}).get("message", {}).get("content", "")).strip()
            return translated or None
        except Exception as exc:
            logger.debug("Ollama translation fallback failed (%s->%s): %s", src, tgt, exc)
            return None

    def translate_with_meta(self, text: str, source_lang: str, target_lang: str) -> Tuple[str, str]:
        value = str(text or "").strip()
        if not value:
            return "", "empty"
        src = self.normalize_lang(source_lang, fallback=self.cfg.default_source_lang)
        if src == "auto":
            src = self.detect_language(value)
        tgt = self.normalize_lang(target_lang, fallback=self.BRIDGE_LANG)
        if not self.cfg.enabled or src == tgt:
            self._last_backend = "passthrough"
            return value, "passthrough"

        key = (value, src, tgt)
        cached = self._cache_get(key)
        if cached is not None:
            self._last_backend = cached[1]
            return cached

        mode = self.cfg.mode
        translated: Optional[str] = None
        backend = "passthrough"

        if mode in {"online_first", "hybrid", "online_only"}:
            translated = self._online.translate(value, src, tgt)
            if translated:
                backend = "online_google"
            elif mode != "online_only":
                translated, backend = self._local.translate(value, src, tgt)
        elif mode in {"local_first", "local_only"}:
            translated, backend = self._local.translate(value, src, tgt)
            if not translated and mode == "local_first":
                translated = self._online.translate(value, src, tgt)
                if translated:
                    backend = "online_google"
        elif mode == "ollama":
            translated = self._translate_ollama(value, src, tgt)
            if translated:
                backend = "ollama"

        if not translated and self.cfg.fallback_to_ollama and mode != "ollama":
            translated = self._translate_ollama(value, src, tgt)
            if translated:
                backend = "ollama_fallback"

        if not translated:
            self._last_backend = "passthrough_fallback"
            return value, "passthrough_fallback"

        self._last_backend = backend
        self._cache_put(key, translated, backend)
        return translated, backend

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        out, _ = self.translate_with_meta(text, source_lang, target_lang)
        return out

    def to_bridge(self, text: str, source_lang: Optional[str]) -> str:
        src = self.normalize_lang(source_lang, fallback=self.cfg.default_source_lang)
        if src == "auto":
            src = self.detect_language(text)
        return self.translate(text, src, self.BRIDGE_LANG)

    def from_bridge(self, text: str, target_lang: Optional[str]) -> str:
        tgt = self.normalize_lang(target_lang, fallback=self.cfg.default_source_lang)
        return self.translate(text, self.BRIDGE_LANG, tgt)

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.cfg.enabled,
            "mode": self.cfg.mode,
            "bridge_lang": self.BRIDGE_LANG,
            "online_cooldown": self._online.in_cooldown(),
            "local_models_dir": str(self.cfg.local_models_dir),
            "last_backend": self._last_backend,
        }


_SHARED_LOCK = threading.Lock()
_SHARED_INSTANCE: Optional[HybridTranslator] = None


def get_shared_translator(
    cfg: Optional[Dict[str, Any]] = None,
    *,
    ollama_client: Any = None,
    refresh: bool = False,
) -> HybridTranslator:
    """Return process-wide shared HybridTranslator singleton."""
    global _SHARED_INSTANCE
    with _SHARED_LOCK:
        if _SHARED_INSTANCE is None or refresh:
            _SHARED_INSTANCE = HybridTranslator(cfg, ollama_client=ollama_client)
        elif cfg is not None and isinstance(cfg, dict):
            # Apply updated config if explicitly supplied on init
            _SHARED_INSTANCE = HybridTranslator(cfg, ollama_client=ollama_client or _SHARED_INSTANCE.ollama_client)
        return _SHARED_INSTANCE


def reset_shared_translator() -> None:
    global _SHARED_INSTANCE
    with _SHARED_LOCK:
        _SHARED_INSTANCE = None


__all__ = [
    "HybridTranslator",
    "HybridTranslatorConfig",
    "get_shared_translator",
    "reset_shared_translator",
    "split_translation_chunks",
]
