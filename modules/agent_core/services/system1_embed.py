from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from modules.agent_core.services.laya_engine import LayaDecision
from modules.agent_core.services.system1_rules import (
    is_conversational_query,
    is_negated_command,
    urgency_bonus,
)

logger = logging.getLogger("agent.system1_embed")

# (target_module, is_direct_command, sample_utterance)
# Includes both literal commands and indirect/implied Turkish utterances.
_INTENT_CORPUS: Tuple[Tuple[str, bool, str], ...] = (
    # --- neopixel (direct & implied lighting/ambiance requests) ---
    ("neopixel", True, "ışığı aç"),
    ("neopixel", True, "ışıkları kapat"),
    ("neopixel", True, "kırmızı yap"),
    ("neopixel", True, "mavi led yak"),
    ("neopixel", True, "yeşili yak"),
    ("neopixel", True, "mor ışık aç"),
    ("neopixel", True, "twinkle efekti başlat"),
    ("neopixel", True, "yanıp sönme animasyonu"),
    ("neopixel", True, "nefes animasyonu aç"),
    ("neopixel", True, "parlaklığı artır"),
    ("neopixel", True, "turn light red"),
    ("neopixel", True, "dim the lights"),
    ("neopixel", True, "ortam çok karanlık oldu"),
    ("neopixel", True, "ortam zifiri karanlık hiçbir şey göremiyorum"),
    ("neopixel", True, "burası çok karanlık önümü göremiyorum"),
    ("neopixel", True, "gözüm önümü görmüyor biraz aydınlat"),
    ("neopixel", True, "bu ışık çok parlak gözümü aldı biraz kıs"),
    ("neopixel", True, "gözlerim kamaştı ışığı azalt"),
    ("neopixel", True, "ortama biraz renk kat"),
    ("neopixel", True, "gece lambasını yak"),
    ("neopixel", True, "uyuyacağım ışıkları söndür"),
    ("neopixel", True, "film izleyeceğiz loş bir ortam yap"),
    ("neopixel", True, "parti havası yarat renkli ışıklar yansın"),
    # --- emergency_stop (direct & implied collision/hazard warnings) ---
    ("emergency_stop", True, "acil dur"),
    ("emergency_stop", True, "hemen dur"),
    ("emergency_stop", True, "dur robot"),
    ("emergency_stop", True, "stop robot emergency stop"),
    ("emergency_stop", True, "tehlike var dur"),
    ("emergency_stop", True, "önünde duvar var çarpacaksın"),
    ("emergency_stop", True, "masanın kenarına geldin düşeceksin"),
    ("emergency_stop", True, "dikkat et önünde engel var"),
    ("emergency_stop", True, "sakın kıpırdama olduğun yerde kal"),
    ("emergency_stop", True, "fren yap motorları durdur"),
    ("emergency_stop", True, "kablo dolandı hareket etme"),
    ("emergency_stop", True, "ayağıma çarpacaksın dur"),
    # --- arduino_serial (direct & implied head/motor movement) ---
    ("arduino_serial", True, "sağa bak"),
    ("arduino_serial", True, "sola dön"),
    ("arduino_serial", True, "kafanı yukarı kaldır"),
    ("arduino_serial", True, "başını aşağı indir"),
    ("arduino_serial", True, "ileri git"),
    ("arduino_serial", True, "geri gel"),
    ("arduino_serial", True, "beni takip et"),
    ("arduino_serial", True, "follow me"),
    ("arduino_serial", True, "sol taraftan garip bir ses geldi oraya bak"),
    ("arduino_serial", True, "sağ tarafta bir tıkırtı var oraya dön"),
    ("arduino_serial", True, "arkanda biri var arkana dön bak"),
    ("arduino_serial", True, "bana doğru yaklaş yanıma gel"),
    ("arduino_serial", True, "biraz geri çekil çok yaklaştın"),
    ("arduino_serial", True, "peşimden gel benden ayrılma"),
    ("arduino_serial", True, "yüzüme bak kafanı kaldır"),
    ("arduino_serial", True, "tavana bak yukarıda bir şey var"),
    ("arduino_serial", True, "yere bak aşağıda ne düştü"),
    # --- camera (direct & implied visual inspection requests) ---
    ("camera", True, "fotoğraf çek"),
    ("camera", True, "kamerayı aç"),
    ("camera", True, "resim çek"),
    ("camera", True, "take a photo"),
    ("camera", True, "görüntüyü kaydet"),
    ("camera", True, "masanın üstünde ne var kontrol et"),
    ("camera", True, "elimdeki nesneye bak ne olduğunu söyle"),
    ("camera", True, "etrafta kimse var mı kamerayla bak"),
    ("camera", True, "karşında kim duruyor yüzünü tanı"),
    ("camera", True, "odada kaç kişi var bak"),
    ("camera", True, "bu anı ölümsüzleştir bir kare yakala"),
    # --- speak (direct & implied audio/voice control) ---
    ("speak", True, "şarkı söyle"),
    ("speak", True, "müzik çal"),
    ("speak", True, "sus sessize geç"),
    ("speak", True, "sing a song"),
    ("speak", True, "be quiet"),
    ("speak", True, "çok gürültü yapıyorsun biraz sessiz ol"),
    ("speak", True, "kafamı şişirdin artık konuşma"),
    ("speak", True, "bize neşeli bir melodi mırıldan"),
    ("speak", True, "bebek uyuyor sesini kıs"),
    ("speak", True, "çok sessiz oldu bize bir şarkı mırıldan"),
    # --- system2_chat (conversational, reflective, or passive observations) ---
    ("system2_chat", False, "bugün nasılsın"),
    ("system2_chat", False, "bana bir hikaye anlat"),
    ("system2_chat", False, "felsefi bir sorum var"),
    ("system2_chat", False, "bugün hava nasıl"),
    ("system2_chat", False, "iyi misin"),
    ("system2_chat", False, "bana bir şiir söyle"),
    ("system2_chat", False, "canım çok sıkılıyor benimle sohbet et"),
    ("system2_chat", False, "bana ilginç bir bilimsel gerçekten bahset"),
    ("system2_chat", False, "bu konuda sen ne düşünüyorsun"),
    ("system2_chat", False, "mavi rengi çok seviyorum bence çok huzurlu"),
    ("system2_chat", False, "kırmızı ışık sence nasıl duruyor"),
    ("system2_chat", False, "ışık söndü galiba elektrikler mi kesildi"),
    ("system2_chat", False, "bugün kendimi biraz yorgun hissediyorum"),
    ("system2_chat", False, "yapay zeka hakkında ne düşünüyorsun"),
)

_AFFECT_CORPUS: Dict[str, Tuple[str, ...]] = {
    "joy": (
        "çok mutluyum harika bir gün",
        "içim kıpır kıpır sevinçten uçuyorum",
        "aferin sana harika iş çıkardın çok sevindim",
        "yaşasın başardık süper oldu",
        "keyfim çok yerinde yüzüm gülüyor",
    ),
    "anger": (
        "sinirlerim tepeme çıktı çok kızgınım",
        "beni çıldırtıyorsun sabrım taştı",
        "öfkeden deliye döndüm yeter artık",
        "bu yaptığına çok sinirlendim berbat",
        "kafamı bozma çok gerginim",
    ),
    "disgust": (
        "midem bulandı çok iğrenç bir şey",
        "leş gibi kokuyor tiksindim",
        "böyle iğrenç ve pis bir görüntü görmedim",
        "kusacağım şimdi çok kötü kokuyor",
        "tüylerim diken diken oldu ne kadar pis",
    ),
    "fear": (
        "ödüm koptu çok korkuyorum",
        "içimde kötü bir his var panik oldum",
        "karanlıktan ve yalnız kalmaktan ürküyorum",
        "tehlikeli bir durum var çok endişeliyim",
        "kalbim küt küt atıyor korkunç bir ses geldi",
    ),
    "curiosity": (
        "acaba bunun içinde ne var çok merak ediyorum",
        "bu sistem nasıl çalışıyor çok ilginç",
        "neden böyle olduğunu anlamak istiyorum",
        "bunu ilk defa görüyorum ne işe yarıyor acaba",
    ),
    "sadness": (
        "içim çok daralıyor kendimi yalnız hissediyorum",
        "bugün moralim çok bozuk üzgünüm",
        "kimse beni anlamıyor çok mutsuzum",
        "hayal kırıklığına uğradım ağlamak istiyorum",
    ),
    "neutral": (
        "normal bir durum her şey yolunda",
        "saat kaç oldu acaba",
        "standart çalışma düzeni devam ediyor",
        "tamam anladım devam edebiliriz",
    ),
}

_AFFECT_SAMPLES: Tuple[Tuple[str, str], ...] = tuple(
    (affect, sample) for affect, samples in _AFFECT_CORPUS.items() for sample in samples
)

# Default action parameter hints for indirect/implied Turkish anchors
_ANCHOR_ACTION_HINTS: Dict[str, Dict[str, Any]] = {
    "ortam çok karanlık oldu": {"tool": "set_lights", "color": "white", "effect": "SOLID"},
    "ortam zifiri karanlık hiçbir şey göremiyorum": {"tool": "set_lights", "color": "white", "effect": "SOLID"},
    "burası çok karanlık önümü göremiyorum": {"tool": "set_lights", "color": "white", "effect": "SOLID"},
    "gözüm önümü görmüyor biraz aydınlat": {"tool": "set_lights", "color": "white", "effect": "SOLID"},
    "bu ışık çok parlak gözümü aldı biraz kıs": {"tool": "set_lights", "color": "orange", "effect": "BREATHE"},
    "gözlerim kamaştı ışığı azalt": {"tool": "set_lights", "color": "orange", "effect": "BREATHE"},
    "gece lambasını yak": {"tool": "set_lights", "color": "orange", "effect": "BREATHE"},
    "film izleyeceğiz loş bir ortam yap": {"tool": "set_lights", "color": "purple", "effect": "BREATHE"},
    "parti havası yarat renkli ışıklar yansın": {"tool": "set_lights", "color": "cyan", "effect": "TWINKLE"},
    "uyuyacağım ışıkları söndür": {"tool": "set_lights", "color": "off", "effect": "OFF"},
    "sol taraftan garip bir ses geldi oraya bak": {"tool": "move_head", "direction": "left"},
    "sağ tarafta bir tıkırtı var oraya dön": {"tool": "move_head", "direction": "right"},
    "tavana bak yukarıda bir şey var": {"tool": "move_head", "direction": "up"},
    "yere bak aşağıda ne düştü": {"tool": "move_head", "direction": "down"},
}


class System1EmbedEngine:
    """ONNX INT8 Semantic Router for System 1 (multilingual-e5-small, ~15-50ms on Pi 5).

    Provides both intent routing (including indirect/implied Turkish utterances)
    and semantic affect classification using a shared singleton ONNX session.
    """

    _instance: Optional["System1EmbedEngine"] = None
    _instance_lock = threading.Lock()

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.model_path = str(cfg.get("model_path", "models/e5-small-onnx"))
        self.threshold_direct = float(cfg.get("threshold_direct", 0.60))
        self.threshold_module = float(cfg.get("threshold_module", 0.50))
        self._session: Any = None
        self._tokenizer: Any = None
        self._matrix: Any = None
        self._affect_matrix: Any = None
        self._lock = threading.Lock()
        self._load_attempted = False
        self._is_available = False
        self._backend_name = "none"

    @classmethod
    def get_instance(cls, cfg: Optional[Dict[str, Any]] = None) -> "System1EmbedEngine":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(cfg)
            return cls._instance

    @property
    def is_available(self) -> bool:
        return self.enabled and self._ensure_loaded()

    def _ensure_loaded(self) -> bool:
        if not self.enabled:
            return False
        if self._is_available:
            return True
        if self._load_attempted:
            return False
        with self._lock:
            if self._load_attempted:
                return self._is_available
            self._load_attempted = True
            t0 = time.perf_counter()
            try:
                import numpy as np
            except ImportError:
                logger.info("numpy missing; embedding backend disabled")
                return False
            matrix = self._load_vectors(np)
            if matrix is None:
                return False
            self._matrix = matrix
            self._affect_matrix = self._embed_passages_onnx(
                [sample for _, sample in _AFFECT_SAMPLES], np
            )
            self._is_available = True
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "System1 embedding backend ready (%s, %d intent + %d affect anchors) in %.1fms",
                self._backend_name,
                matrix.shape[0],
                len(_AFFECT_SAMPLES),
                elapsed_ms,
            )
            return True

    def _load_vectors(self, np: Any) -> Any:
        onnx_file = os.path.join(self.model_path, "model.onnx")
        if os.path.isdir(self.model_path) and os.path.isfile(onnx_file):
            self._session = self._load_onnx(onnx_file)
            if self._session is not None:
                self._backend_name = "onnxruntime"
                return self._embed_passages_onnx(
                    [sample for _, _, sample in _INTENT_CORPUS], np
                )
        logger.info(
            "ONNX embedding model not found at %s (backend=%s); semantic router disabled",
            self.model_path,
            self._backend_name,
        )
        self._backend_name = "missing"
        return None

    def _load_onnx(self, onnx_file: str) -> Any:
        try:
            import onnxruntime
        except ImportError:
            self._backend_name = "onnx-missing"
            return None
        try:
            opts = onnxruntime.SessionOptions()
            opts.log_severity_level = 3
            opts.intra_op_num_threads = 2
            opts.inter_op_num_threads = 1
            return onnxruntime.InferenceSession(
                onnx_file,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            logger.warning("onnx session build failed: %s", exc)
            return None

    def _e5_mean_pooled(self, hidden: Any, attention: Any, np: Any) -> Any:
        mask = np.asarray(attention, dtype="float32")
        hidden = np.asarray(hidden, dtype="float32")
        summed = (hidden * mask[:, :, None]).sum(axis=1)
        counts = np.clip(mask.sum(axis=1, keepdims=True), 1e-9, None)
        vecs = summed / counts
        norms = np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9, None)
        return vecs / norms

    def _embed_passages_onnx(self, samples: List[str], np: Any) -> Any:
        vecs = []
        for sample in samples:
            feed = self._tok_onnx([f"passage: {sample}"])
            vecs.append(self._onnx_vecs(feed, np)[0])
        return np.stack(vecs).astype("float32")

    def _tok_onnx(self, texts: List[str]) -> Dict[str, Any]:
        if self._tokenizer is None:
            try:
                from tokenizers import Tokenizer as _HFTokenizers

                self._tokenizer = _HFTokenizers.from_file(
                    os.path.join(self.model_path, "tokenizer.json")
                )
            except Exception as exc:
                logger.warning("tokenizer load failed: %s", exc)
                return {"input_ids": [], "attention_mask": []}
        enc = self._tokenizer.encode_batch(texts)
        ids = [list(t.ids) for t in enc]
        masks = [[1] * len(row) for row in ids]
        feed: Dict[str, Any] = {"input_ids": ids, "attention_mask": masks}
        try:
            required = {str(i.name) for i in self._session.get_inputs()}
        except Exception:
            return feed
        if "token_type_ids" in required:
            feed["token_type_ids"] = [[0] * len(row) for row in ids]
        return feed

    def _onnx_vecs(self, feed: Dict[str, Any], np: Any) -> Any:
        outs = self._session.run(None, feed)
        for out in outs:
            arr = np.asarray(out, dtype="float32")
            if arr.ndim == 3:
                return self._e5_mean_pooled(arr, feed["attention_mask"], np)
        for out in outs:
            arr = np.asarray(out, dtype="float32")
            if arr.ndim == 2:
                norms = np.clip(np.linalg.norm(arr, axis=1, keepdims=True), 1e-9, None)
                return arr / norms
        return np.zeros((len(feed["input_ids"]), 1), dtype="float32")

    def _classify_affect_vec(self, query_vec: Any, np: Any) -> Tuple[str, float]:
        if self._affect_matrix is None:
            return "neutral", 0.5
        affect_scores = self._affect_matrix @ query_vec
        top_idx = int(np.argmax(affect_scores))
        best_sim = float(affect_scores[top_idx])
        mean_sim = float(np.mean(affect_scores))
        affect_label = _AFFECT_SAMPLES[top_idx][0]
        # Require a clear margin over the corpus average to avoid false emotions on hardware commands
        margin = best_sim - mean_sim
        if best_sim < 0.82 or margin < 0.04:
            return "neutral", 0.55
        conf = round(min(0.95, max(0.60, 0.60 + margin * 4.5)), 3)
        return affect_label, conf

    def decide(self, text: str) -> Optional[LayaDecision]:
        if not self._ensure_loaded():
            return None
        cleaned = str(text or "").strip()
        if not cleaned:
            return None
        t0 = time.perf_counter()
        query_vec = self._embed_query(cleaned)
        if query_vec is None:
            return None
        import numpy as np

        scores = self._matrix @ query_vec
        top_idx = int(np.argmax(scores))
        best_score = float(scores[top_idx])
        mean_score = float(np.mean(scores))
        target, anchor_is_direct, matched_sample = _INTENT_CORPUS[top_idx]

        module_conf = self._calibrate(best_score, mean_score)
        if module_conf < self.threshold_module:
            self._log_dec(cleaned, target, module_conf, t0, rejected=True)
            return None

        affect_label, affect_conf = self._classify_affect_vec(query_vec, np)
        negated = is_negated_command(cleaned)
        conversational = is_conversational_query(cleaned)
        if negated or conversational:
            is_direct = False
            if negated and target != "system2_chat":
                target = "system2_chat"
        elif affect_label != "neutral" and affect_conf >= 0.80 and module_conf < affect_conf:
            target = "system2_chat"
            is_direct = False
        else:
            is_direct = bool(anchor_is_direct and module_conf >= self.threshold_direct)

        direct_conf = round(module_conf if is_direct else max(0.65, 1.0 - module_conf * 0.3), 3)

        urg_bonus = urgency_bonus(cleaned)
        if target == "emergency_stop" and is_direct:
            urg_score = max(2.8, urg_bonus)
            urg_conf = max(0.86, round(module_conf, 3))
        else:
            urg_score = urg_bonus
            urg_conf = 0.65

        reason = "embedding_direct" if is_direct else "embedding_conversation"
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        action_hint = _ANCHOR_ACTION_HINTS.get(matched_sample) if is_direct else None
        raw_answers: Dict[str, Any] = {
            "backend": "embed",
            "rule": reason,
            "matched_anchor": matched_sample,
            "raw_similarity": round(best_score, 4),
            "target_module": {
                "type": "choice",
                "choice": target,
                "confidence": round(module_conf, 3),
            },
            "is_direct_command": {
                "type": "choice",
                "choice": "direct_action" if is_direct else "conversation",
                "confidence": direct_conf,
            },
            "affective_event": {
                "type": "choice",
                "choice": affect_label,
                "confidence": affect_conf,
            },
        }
        if action_hint:
            raw_answers["action_hint"] = dict(action_hint)
        decision = LayaDecision(
            target_module=target,
            module_confidence=round(module_conf, 3),
            is_direct_command=is_direct,
            direct_confidence=direct_conf,
            affective_event=affect_label,
            affect_confidence=affect_conf,
            urgency_score=urg_score,
            urgency_confidence=urg_conf,
            inference_ms=elapsed_ms,
            raw_answers=raw_answers,
        )
        logger.debug(
            "embed decision: target=%s direct=%s affect=%s score=%.3f conf=%.3f in %.2fms",
            target,
            is_direct,
            affect_label,
            best_score,
            module_conf,
            elapsed_ms,
        )
        return decision

    def _calibrate(self, sim: float, mean_sim: float = 0.78) -> float:
        # E5 cosine similarities live in [0.74, 0.94]; combine absolute score and margin over mean
        margin = max(0.0, sim - mean_sim)
        stretched = (sim - 0.72) / 0.18
        blended = 0.65 * stretched + 0.35 * min(1.0, margin / 0.07)
        return float(max(0.0, min(0.98, blended)))

    @staticmethod
    def _strip_e5_prefix(text: str) -> str:
        s = str(text or "").strip()
        for prefix in ("query:", "passage:"):
            while s.lower().startswith(prefix):
                s = s[len(prefix) :].strip()
        return s

    def _embed_prefixed(self, prefix: str, text: str) -> Any:
        if self._backend_name == "onnxruntime":
            import numpy as np

            cleaned = self._strip_e5_prefix(text)
            if not cleaned:
                return None
            feed = self._tok_onnx([f"{prefix}: {cleaned}"])
            if not feed["input_ids"]:
                return None
            vecs = self._onnx_vecs(feed, np)
            return np.asarray(vecs[0], dtype="float32")
        return None

    def _embed_query(self, cleaned: str) -> Any:
        return self._embed_prefixed("query", cleaned)

    def _log_dec(self, cleaned: str, label: str, conf: float, t0: float, rejected: bool = False) -> None:
        logger.debug(
            "embed %s intent=%s conf=%.3f in %.2fms",
            "rejected" if rejected else "accepted",
            label,
            conf,
            (time.perf_counter() - t0) * 1000.0,
        )

    def embed_vector(self, text: str) -> Any:
        if not self._ensure_loaded():
            return None
        raw = str(text or "").strip()
        prefix = "passage" if raw.lower().startswith("passage:") else "query"
        vec = self._embed_prefixed(prefix, raw)
        if vec is None:
            return None
        import numpy as np

        arr = np.asarray(vec, dtype="float32")
        norm = float(np.linalg.norm(arr)) or 1.0
        return arr / norm

    def embed_passage(self, text: str) -> Any:
        if not self._ensure_loaded():
            return None
        vec = self._embed_prefixed("passage", str(text or ""))
        if vec is None:
            return None
        import numpy as np

        arr = np.asarray(vec, dtype="float32")
        norm = float(np.linalg.norm(arr)) or 1.0
        return arr / norm

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "available": self._is_available,
            "backend": self._backend_name,
            "model_path": self.model_path,
            "corpus_size": len(_INTENT_CORPUS),
            "affect_corpus_size": len(_AFFECT_SAMPLES),
            "thresholds": [self.threshold_module, self.threshold_direct],
        }


__all__ = ["System1EmbedEngine"]
