# Laya System 1 Entegrasyonu — YAPILACAK İŞLER (İmplementasyon Kılavuzu)

> **Amaç:** Bu dosya, token/bağlam bittiğinde başka bir AI modelinin devam edebilmesi için yazılmıştır.
> **Önkoşul:** Önce `laya_integration_completed.md` dosyasını oku — ne yapıldığını anla.
> **Kural:** Silme yapma, mevcut kodu boz**ma**. Additive (eklemeli) çalış.
> **Config:** Hardcode yasak, her şey `config/agent.yaml`'dan okunmalı.
> **Test:** Her faz sonunda `pytest tests -x -q` çalıştır; son doğrulanmış toplam 970 testtir (yeni test eklenirse sayı değişir).

> **Güncel durum / karar (2026-09-27):** Güvenli, dispatch kapalı Laya System 1 entegrasyonu bu faz için tamamlandı. Üretimde `tri_layer.laya.enabled: true`, ancak `action_proposals.enabled: false`; Laya önerisi ToolRegistry yürütmesine yetki vermez. Son doğrulama: tam test paketi **970 passed**; değişen Python modüllerinin `py_compile` ve çalışma ağacı `git diff --check` temiz. Tamamlananlar ve kalan rollout kapıları aşağıda. Aşağıdaki eski tarihler, kararların deney günlüğüdür; güncel durum için bu blok ve `laya_integration_completed.md` önceliklidir.
>
> **Yapılanlar:** LayaEngine/Agent entegrasyonu, kısa doğrudan komut ile System 2 sohbet sınırı, affect/vision olayları ve güven eşikleri; typed `set_lights` inert proposal builder + exact schema validator; turn başına internal UUID bağlama; çevrimdışı evaluator, renk/intent/audio dev ve holdout ölçümleri; parser adaylarının reddi; testler ve güvenlik/rollout dokümanları.
>
> **Sıradaki işler (release sırası):**
> 1. Proje sahibi tarafından haricen gözden geçirilmiş, yeterli büyüklükte ve sınıfları dengeli intent/safety etiket seti sağla; mevcut holdout'lar tüketildi, tuning için tekrar kullanma.
> 2. Laya-origin ışık eylemi için Autonomy runtime owner capability approval/deny kapısı tasarla ve uygula. Mevcut `set_lights` uyumluluk handler'ı ActionArbiter/ActionSafetyFilter + ışık lease kullanıyor ama CapabilityExecutor'a girmiyor; bu gate olmadan dispatch yapılmayacak.
> 3. Gate ile birlikte simülasyon testlerini ekle: stale/wrong-request/low-confidence/unknown-args/disabled/capability-denied önerilerinde `ToolRegistry.execute`, handler ve hardware çağrısı sıfır; yalnız açıkça onaylı fixture eylemi mock owner yoluna gider.
> 4. Uyumlu gerçek Laya runtime ve hedef Raspberry Pi üzerinde target/direct/emergency/effect kalite ve gecikme kabulünü ölç.
> 5. Emergency stop'u SpinalCord + Arduino authoritative contract/ACK yolunda ayrı uygula ve test et.
> 6. Yukarıdakilerin tümü, cancellation/cooldown, arbiter, ACK/timeout ve arbitrary-output fail-closed testleri geçmeden `action_proposals.enabled` açılmayacak.
>
> **Rollout tamamlanma koşulu:** Haricen gözden geçirilmiş veri ölçütleri, Autonomy capability ownership, sıfır yan-etki ret testleri, acil-stop regresyonları ve Pi donanım kabulünün hepsi yeşil. O zamana kadar mevcut güvenli kapanış durumu korunur; feature açılmaması eksik kod değil bilinçli release gate'idir.
>
> **Devam notu (2026-09-25):** `laya_integration_completed.md` son bölümlerini oku. Faz 5.1–5.2 ve 6.1–6.4 kararları işlendi; Faz 7 regression kapsaması genişletildi. Faz 2.6/2.7 ve 3.8 için mimari değerlendirme eklendi. Faz 3.1 doğrudan tool dispatch'i güvenli argüman/actuator sözleşmesi olmadan uygulanmamalı. Agent adaptörünün kararı cache'lemesi, kısa sohbeti System 2'ye bırakması ve karar aşamasında tool çalıştırmaması için ek regression testleri mevcut. Tam test paketi hazır Python 3.12 runtime ile runtime site-packages yolunu `.venv`'den önce vererek çalıştırılabiliyor; son tam koşu 940 test geçti.
>
> **Devam (2026-09-25):** Fail-closed, yalnızca öneri üreten `set_lights` typed-choice builder eklendi (`modules/agent_core/services/laya_action_contract.py`). Feature `config/agent.yaml` içinde kapalı; direct dispatch bağlantısı yok. Sonraki adım, uyumlu runtime/Pi'de gerçek modelle ek `action_color`/`action_effect` sorularını doğrulamak. Başarılı olursa validator eşik ve model kalibrasyonu gözden geçirilir; sonrasında ancak ToolRegistry + arbiter + Autonomy capability/safety üzerinden dispatch değerlendirilir. Emergency motor-stop ayrı SpinalCord/Arduino işi olarak kalır.
>
> **Gerçek model güvenlik bulgusu (2026-09-25):** Python 3.11 ile cache model inference çalıştı. `Işıkları kapat` eski predicate'e göre false emergency olurdu (emergency_stop confidence 0.8273, direct 0.8297, urgency 2.059/confidence 0.541); sıradan sohbet urgency 2.4434/confidence 0.2844 üretti. Bu nedenle emergency artık yüksek confidence'lı direct emergency target veya confidence'lı urgency gerektiriyor; normal high-urgency yan etkileri de urgency confidence threshold'una bağlı. Açık acil stop örnekleri target 0.934/direct 0.982 ve target 0.950/direct 0.970 ile geçiyor. Renk çıkarımı `mavi` isteğinde `pink`/0.289 güven verdiği için action proposal kapalı kalmalı. Test/doküman güncellendi.
>
> **Action calibration (2026-09-25):** `tools/evaluate_laya_action_proposals.py` 14 sabit Türkçe örneği çalıştırır ve hiçbir donanım/action API çağırmaz. Gerçek model: target top-choice 0.643; confidence>=0.60 coverage 0.571 ve kabul edilen hedef doğruluğu 0.625. Direct top-choice 0.929; coverage 0.357 ve kabul edilen direct doğruluğu 1.0. Explicit color 1/8 (0.125), explicit effect 2/3, confidence-gated emergency 14/14, öneri 0. Raporlama metriğindeki unspecified renk yanlış sayım düzeltildi. Renk/target/direct coverage öneri üretmeye yetersiz; feature `enabled: false` kalmalı. Daha geniş holdout + soru varyantı kalibrasyonu direct dispatcher'dan önce.
>
> **Soru varyantı deneyi (2026-09-25):** Aynı batch içinde mevcut, açık Türkçe ve açık İngilizce/bilingual color prompt'ları karşılaştırıldı. İki alternatif de açık renk isteklerinde 8/8 doğru, confidence>=0.85 coverage 7/8 verdi; fakat altı no-color kontrolünde doğru unspecified oranı sırasıyla 1/6 ve 2/6, her varyantta iki high-confidence yanlış renk vardı. Mevcut prompt explicit renk 1/8 ama no-color specificity 5/6 ve high-confidence false positive 0. Hiçbir varyant production'a alınmadı; `action_proposals.enabled: false` kalıyor.
>
> **Birleşik seçim deneyi (2026-09-25):** Tek finite-choice sorusunda renk, ışığı kapatma ve ışık komutu olmama seçenekleri birleştirildi. Aynı 14 örnekte genel doğruluk 0.500; açık renk doğruluğu 0.750, confidence>=0.85 coverage 0.375 ve kabul edilen renk doğruluğu 1.000 oldu. Altı no-color kontrolünde specificity 0.167 ve 3 high-confidence yanlış seçim görüldü. Bu soru da güvenli değil; production soruları ve kapalı proposal ayarı değişmedi. Sonraki calibration işi, aynı örneklerin varyantlarını optimize etmek yerine daha geniş, önceden etiketlenmiş ve ayrık holdout Türkçe kümesi oluşturmaktır.
>
> **Genişletilmiş calibration kümesi (2026-09-25):** Evaluator 32 elle etiketlenmiş Türkçe örneğe genişletildi: 18 explicit color/off ve 14 no-explicit-color kontrolü. Current question explicit doğruluk 0.111 / specificity 0.857 / high-confidence FP 0; Türkçe varyant 1.000 / coverage 0.778 / specificity 0.214 / FP 4; İngilizce-bilingual 0.944 / coverage 0.889 / specificity 0.286 / FP 5. Birleşik soru overall 0.625, explicit-color 0.778, coverage 0.222, specificity 0.429, FP 4. Emergency 32/32 ve proposal 0. Kalibrasyon kümesi bağımsız holdout değildir; hiçbir varyant production'a alınmadı. Sıradaki iş: ayrı, önceden tanımlanmış holdout set oluşturmak ve rule-based explicit command baseline'ını da aynı metriklerle ölçmek.
>
> **Ayrı final holdout + parser baseline (2026-09-25):** Kalibrasyon ve parser geliştirme cümlelerinden ayrık 30 örnekli final set (14 explicit color/off, 16 control) sabitlendi. Deterministik parser 0.967 overall / 0.929 explicit doğruluk / 1.000 control specificity verdi. Laya current/TR-explicit/EN-explicit/joint overall sırasıyla 0.433/0.533/0.567/0.500; explicit doğruluk 0.143/1.000/1.000/0.786, specificity 0.688/0.125/0.188/0.250. TR/EN varyantları 8/9 yüksek güvenli false positive üretti. Parser yalnız evaluator içinde ve holdout'a bakılarak değiştirilmeyecek; yeni ayar yapılacaksa yeni final split gerekir. Action proposal kapalı kalır. Sıradaki iş: parser'ı daha geniş, insan tarafından gözden geçirilmiş yeni bağımsız veriyle test etmek; ardından typed proposal'ın target/direct/effect kapılarını ve simüle dispatch safety yolunu ayrı değerlendirmek.
>
> **Intent/safety final holdout (2026-09-25):** Renk setlerinden ayrık 30 örnek, altı target sınıfının her birinden beş örnek. Target doğruluğu 0.600 (neopixel 0.400, arduino_serial 1.000, emergency_stop 0.800, speak 0.200, camera 1.000, system2_chat 0.200); confidence>=0.60 coverage 0.700, kabul edilen target doğruluğu 0.714. Direct doğruluk 0.900; coverage 0.700, kabul edilen doğruluk 1.000. Emergency doğruluğu 0.933, FP 0, FN 2; high urgency doğruluğu 0.833, FP 0, FN 5. Effect doğruluğu 2/4 ve confidence>=0.85 kabulü 0/4. Bu holdout'a göre ayar yapılmadı. Sıradaki geliştirme işi yeni dev set'te `speak/system2_chat` ve acil durum recall'ını, ayrıca effect confidence'ını iyileştirip daha sonra yeni untouched holdout hazırlamak; dispatcher hâlâ kapalı.
>
> **Target/effect prompt calibration (2026-09-25):** 32 örnekli yalnız dev setinde uzun TR target varyantı accuracy 0.188 / accepted accuracy 0.174 / coverage 0.719; kısa EN target varyantı 0.500 / accepted accuracy 0.667 / coverage 0.188 oldu. Explicit effect varyantı beş etiketli örnekte 0.800 top-choice ama 0.400 coverage ve 0.500 accepted accuracy verdi. Hiçbiri yeterli değil; final intent holdout'a uygulanmadı, production promptları değişmedi.
>
> **Yeni dengeli intent dev + tek sefer holdout karşılaştırması (2026-09-26):** Altı target sınıfından beşer örnekli yeni dev setinde current target 0.467 accuracy/0.667 accepted accuracy/0.500 coverage; Türkçe explicit 0.500/0.857/0.467; English explicit 0.600/0.786/0.467. Türkçe candidate emergency FN'yi dev'de 3'ten 2'ye indirdi; seçilip holdout'ta tek kez denendi fakat target accuracy 0.600'den 0.433'e, accepted accuracy 0.714'ten 0.647'ye, emergency doğruluğu 0.933'ten 0.900'e geriledi (FN 2→3). Candidate reddedildi; production değişmedi. Holdout artık tüketildi; yeni prompt adayı için yeni, untouched test set gereklidir. Direct ve effect/urgency kapıları da aşağıdaki metrikler nedeniyle açık.
>
> **Explicit audio refiner deneyi (2026-09-26):** Ayrı ikili ses üretme komutu sorusu dev setinde 0.733 doğruluk verdi ancak precision=0.0, recall=0.0 (FP 3, 5 speak isteğinin tamamı kaçtı). Confidence 0.60/0.80/0.90 kapılarında speak/system2_chat refinement genel accuracy'yi değiştirmedi (0.467). Candidate reddedildi; production yolu ve daha önce tüketilmiş holdout değiştirilmedi.
>
> **Çıktı araştırması (2026-09-25):** Kurulu Laya 0.3.5 `system_one()` kaynak kodu yalnız `choice`, `score`, `noul` türlerini ve typed confidence/probability cevaplarını destekliyor; serbest JSON action argümanı yok. Sonraki güvenli prototip yalnız bounded choice alanlarını birleştirebilir, sürekli actuator değeri üretemez. Cache snapshot ile gerçek inference denemesi `.venv` Torch `torch_python.dll` yüklenemediği için WinError 126 ile durdu. CP312 Torch wheel kurulumu onaylandı ancak 124.1 MB wheel indirmesi 7.6 MB'ta yaklaşık 73 kB/s hızla takılıp tekrarlı bağlantı kesintisi verdi; paket kurulmadan deneme durduruldu. Gerçek model doğrulaması uyumlu runtime/Pi üzerinde yapılmalı; bu doğrulanmadan dispatch açılmamalı.

---

## GENEL MİMARİ KURAL

```
LayaEngine.get_instance(config) → TEK singleton instance
Tüm modüller AYNI instance'ı kullanır. Yeni instance OLUŞTURMA.
```

---

## FAZ 1: Laya Engine Çekirdek Genişletme + Config

### 1.1 — config/agent.yaml'a Laya section ekle

**Dosya:** `config/agent.yaml`
**Konum:** `tri_layer:` bölümünün içine, `router:` ile aynı seviyede

```yaml
tri_layer:
  enabled: false
  api_native_tools: true
  laya:                                   # ← BU BLOĞU EKLE
    enabled: true
    confidence_threshold: 0.60
    model_path: null
    fast_path:
      enabled: true
      emergency_bypass_safety: true
    filler:
      enabled: true
      cooldown_s: 12.0
      mood_aware: true
    affective:
      mood_impact_scale: 1.0
      vision_events: true
      face_emotion_events: true
    telemetry:
      log_decisions: true
      histogram_enabled: false
    urgency:
      emergency_threshold: 2.0
      high_threshold: 1.5
      sensor_boost_hz: 5.0
  fast_path:
    # ... mevcut fast_path aynen kalır
```

### 1.2 — LayaEngine.decide_with_context() ekle

**Dosya:** `modules/agent_core/services/laya_engine.py`
**Konum:** `decide()` metodundan sonra (satır 285 civarı)
**Ne yapacak:** WorldState + VLM context'i de alarak zenginleştirilmiş karar üretir.

```python
def decide_with_context(
    self,
    text: str,
    world_state: Optional[Dict[str, Any]] = None,
    visual_context: Optional[str] = None,
) -> Optional[LayaDecision]:
    """Context-enriched System 1 decision.
    
    Eğer visual_context varsa, text'e eklenerek Laya'ya gönderilir.
    WorldState bilgisi (battery, mood, follow_active) kararı etkileyebilir.
    """
    enriched = str(text or "").strip()
    if visual_context:
        enriched = f"{enriched} [Sahne: {visual_context[:100]}]"
    
    decision = self.decide(enriched)
    if decision is None:
        return None
    
    # WorldState override'ları
    if world_state:
        battery = world_state.get("battery_percent", 100)
        if battery < 15 and decision.urgency_score < 1.5:
            decision.urgency_score = 1.5  # Düşük batarya → urgency artır
    
    return decision
```

### 1.3 — LayaEngine telemetri ekle

**Dosya:** `modules/agent_core/services/laya_engine.py`
**Konum:** `__init__` içine (satır 132 civarı)

```python
# __init__ içine ekle:
self._decision_count = 0
self._total_inference_ms = 0.0
self._last_decisions: List[Dict[str, Any]] = []  # son 20 karar logu
self._max_decision_log = 20

# decide() metodunun sonuna (return'den önce) ekle:
self._decision_count += 1
self._total_inference_ms += elapsed_ms
self._last_decisions.append({
    "text": cleaned[:50],
    "target": target_mod,
    "conf": target_conf,
    "urgency": urgency_score,
    "ms": elapsed_ms,
})
if len(self._last_decisions) > self._max_decision_log:
    self._last_decisions = self._last_decisions[-self._max_decision_log:]
```

Yeni metod ekle:
```python
def get_telemetry(self) -> Dict[str, Any]:
    """Returns Laya performance telemetry."""
    avg_ms = (self._total_inference_ms / self._decision_count) if self._decision_count > 0 else 0.0
    return {
        "available": self._is_available,
        "enabled": self.enabled,
        "decision_count": self._decision_count,
        "avg_inference_ms": round(avg_ms, 2),
        "load_time_ms": self._load_time_ms,
        "last_decisions": list(self._last_decisions[-5:]),
    }
```

### 1.4 — LayaEngine filler mood-aware yap

**Dosya:** `modules/agent_core/services/laya_engine.py`
**Konum:** `get_instant_filler()` metodunu genişlet

```python
def get_filler_with_affect(self, language: str = "tr", mood: str = "neutral") -> str:
    """Mood'a göre uyarlanmış thinking filler."""
    if mood in ("joy", "curiosity"):
        fillers_tr = ["Hemen bakıyorum!", "Ooo, ilginç bir soru!", "Bakalım ne bulacağım..."]
        fillers_en = ["Oh, interesting!", "Let me check!", "Curious about that..."]
    elif mood in ("sadness", "tired"):
        fillers_tr = ["Hmm, bakayım...", "Bir kontrol edeyim...", "Düşünüyorum..."]
        fillers_en = ["Let me see...", "Thinking...", "Hmm..."]
    elif mood in ("anger", "furious"):
        fillers_tr = ["Tamam, hemen bakıyorum.", "Bir dakika.", "İnceliyorum."]
        fillers_en = ["Fine, checking.", "One moment.", "Looking into it."]
    else:
        return self.get_instant_filler(language)
    
    lang = str(language or "tr").lower()
    if lang.startswith("en"):
        return random.choice(fillers_en)
    return random.choice(fillers_tr)
```

---

## FAZ 2: AutonomyBrain Entegrasyonu

### 2.1 — BrainInitMixin'e LayaEngine ekle

**Dosya:** `modules/autonomy/services/brain_init.py`
**Konum:** `_init_components()` metodunun içi, `self.mood = MoodManager(config)` satırından sonra (satır 56 civarı)

```python
# Import (dosya başına):
from modules.agent_core.services.laya_engine import LayaEngine

# _init_components() içinde, self.mood satırından sonra:
self.laya_engine = LayaEngine.get_instance(config)
```

### 2.2 — AutonomyBrain._think() Laya-aware yap

**Dosya:** `modules/autonomy/services/brain.py`
**Konum:** `_think()` metodu var mı kontrol et. Yoksa `_loop()` içindeki `self._think()` çağrısını bul.

`_think()` metodu brain_parts/ mixin'lerinden geliyor olabilir. Eğer `DecisionMixin` içindeyse orada değişiklik yap. Aramak için:
```
grep -rn "_think" modules/autonomy/services/brain_parts/
```

Yapılacak değişiklik: `_think()` içinde (veya BrainDecisionMixin'de):
```python
# Mevcut _think() veya karar döngüsü içine ekle:
if hasattr(self, 'laya_engine') and self.laya_engine.is_available:
    # Son konuşma metnini al
    last_speech = self.state.get("last_speech_text", "")
    if last_speech:
        laya_dec = self.laya_engine.decide(last_speech)
        if laya_dec:
            # 1. Emergency handling
            if laya_dec.is_emergency:
                self.handle_hardware_event("emergency_voice", {"source": "laya"})
            
            # 2. Mood update
            if laya_dec.affective_event != "neutral":
                self.mood.apply_affective_event(laya_dec.affective_event)
            
            # 3. Curiosity boost from vision
            if laya_dec.target_module == "camera":
                self.mood.modify("curiosity", 15)
```

### 2.3 — System1ReflexEngine → Deprecation Proxy

**Dosya:** `modules/autonomy/services/system1_reflex.py`
**Strateji:** Sınıfı **silme**, mevcut API'yi koru ama implementasyonu LayaEngine'e yönlendir.

```python
"""System 1 Reflex Engine — DEPRECATED: LayaEngine proxy.

Bu sınıf geriye dönük uyumluluk için korunmaktadır.
Tüm işlevsellik artık modules.agent_core.services.laya_engine.LayaEngine tarafından sağlanır.
"""
from __future__ import annotations
import logging
from typing import Any, Dict

logger = logging.getLogger("autonomy.system1_reflex")

# Eski sabitler — backward compat
THINKING_FILLERS_TR = [
    "Hmm...", "Hemen bakıyorum...", "Bir düşüneyim...", "Hımm, anladım...", "Bakalım...",
]
THINKING_FILLERS_EN = [
    "Hmm...", "Let me check...", "Thinking...", "One second...",
]

class System1ReflexEngine:
    """DEPRECATED — LayaEngine'e proxy. Eski API'yi korur."""
    
    def __init__(self, language: str = "tr") -> None:
        self.language = language
        self._laya = None
        self._last_filler_ts = 0.0
        self._filler_cooldown_s = 15.0
        logger.info("System1ReflexEngine initialized as LayaEngine proxy")
    
    def _get_laya(self):
        if self._laya is None:
            try:
                from modules.agent_core.services.laya_engine import LayaEngine
                self._laya = LayaEngine.get_instance()
            except Exception:
                pass
        return self._laya
    
    def get_thinking_body_pose(self) -> Dict[str, Any]:
        laya = self._get_laya()
        if laya:
            reaction = laya.get_affective_reaction("neutral")
            return {
                "head": {"pan": 86, "tilt": 102},
                "ears": {"left": 80, "right": 70},
                "eyes": {"mode": "animation", "name": "thinking"},
                "leds": {"mode": "thinking", "color": reaction.get("led_color", "#30e3ca")},
            }
        # Orijinal fallback
        import random
        return {
            "head": {"pan": random.choice([86, 94]), "tilt": 102},
            "ears": {"left": 80, "right": 70},
            "eyes": {"mode": "animation", "name": "thinking"},
            "leds": {"mode": "thinking", "color": "#30e3ca"},
        }
    
    def should_emit_verbal_filler(self, wait_elapsed_s: float) -> bool:
        import time
        if wait_elapsed_s < 1.2:
            return False
        now = time.time()
        if now - self._last_filler_ts < self._filler_cooldown_s:
            return False
        self._last_filler_ts = now
        return True
    
    def get_verbal_filler(self) -> str:
        laya = self._get_laya()
        if laya:
            return laya.get_instant_filler(self.language)
        import random
        if self.language.startswith("en"):
            return random.choice(THINKING_FILLERS_EN)
        return random.choice(THINKING_FILLERS_TR)
```

### 2.4 — SpinalCordReflex — Sesli acil dur desteği

**Dosya:** `modules/autonomy/services/spinal_cord_reflex.py`
**Konum:** `observe_hardware_event()` metodundan sonra yeni metod ekle

```python
def observe_voice_emergency(self, laya_decision) -> bool:
    """Laya emergency kararını spinal cord refleksine bağlar.
    
    Args:
        laya_decision: LayaDecision instance (laya_engine.py'den)
    Returns:
        True if emergency reflex triggered
    """
    if not self.enabled:
        return False
    if not hasattr(laya_decision, 'is_emergency') or not laya_decision.is_emergency:
        return False
    
    import time
    now = time.time()
    if now - self._last_reflex_ts < self.reflex_cooldown_s:
        return False
    
    logger.warning("SPINAL CORD REFLEX: Voice emergency detected via Laya! target=%s urgency=%.1f",
                    laya_decision.target_module, laya_decision.urgency_score)
    
    self.client.push_interaction_event("motor.stop", {"priority": "emergency", "source": "laya_voice"})
    self._last_reflex_ts = now
    
    try:
        self.memory.add_event(
            f"Voice emergency detected: urgency={laya_decision.urgency_score:.1f}. "
            "Motor stopped via spinal cord reflex."
        )
        self.client.update_emotions(["surprise"])
        self.client.push_interaction_event("appraisal:shocked")
    except Exception as exc:
        logger.error("Failed to notify higher brain of voice emergency: %s", exc)
    
    return True
```

### 2.5 — MoodManager — Tam LayaDecision desteği

**Dosya:** `modules/autonomy/services/mood.py`
**Konum:** `apply_affective_event()` metodundan sonra

```python
def apply_laya_decision(self, decision) -> str:
    """Apply full Laya System 1 decision to mood state.
    
    Args:
        decision: LayaDecision instance
    Returns:
        Dominant emotion string
    """
    with self._lock:
        # 1. Affective event
        if hasattr(decision, 'affective_event'):
            self.apply_affective_event(decision.affective_event)
        
        # 2. Urgency → fear/energy impact
        if hasattr(decision, 'urgency_score'):
            urg = float(decision.urgency_score)
            if urg >= 2.0:
                self.modify("fear", min(40, urg * 15))
                self.modify("energy", -10)
            elif urg >= 1.0:
                self.modify("curiosity", 10)
        
        # 3. Direct command satisfaction
        if hasattr(decision, 'is_direct_command') and decision.is_direct_command:
            self.satisfy_need("stimulation", 15)
        
        # 4. Social interaction
        if hasattr(decision, 'target_module'):
            if decision.target_module == "system2_chat":
                self.satisfy_need("social", 20)
    
    return self.get_dominant_emotion()
```

### 2.6 — BehaviorComposer Laya entegrasyonu

**Durum: Mevcut mood zinciriyle karşılandı (2026-09-25).** Laya affect MoodManager'ı günceller; BehaviorComposer konuşmayı `_speak_with_mood()`'a verir ve bu yol güncel dominant mood'dan tone üretir. Regression testi `test_behavior_composer_speech_uses_current_laya_updated_mood_tone` bu uçtan uca delegeyi doğrular. Composer'a ikinci Laya plan/mood seçicisi eklenmiyor; mevcut safety/plan owner korunuyor.

**Dosya:** `modules/autonomy/services/behavior_composer.py`
**Strateji:** Dosyayı oku, `compose()` veya `select_behavior()` gibi ana metodu bul.
O metodun içinde Laya affective state'e göre behavior chain seçimi ekle.

```python
# Önce dosyayı oku:
# grep -n "def compose\|def select_behavior\|def plan" modules/autonomy/services/behavior_composer.py

# Ana metod içinde, mevcut behavior seçimi yapıldıktan sonra:
laya_engine = getattr(self, '_laya_engine', None)
if laya_engine is None:
    try:
        from modules.agent_core.services.laya_engine import LayaEngine
        self._laya_engine = LayaEngine.get_instance()
        laya_engine = self._laya_engine
    except Exception:
        pass

# Laya decision varsa behavior'ı etkile:
# (Bu kodun tam konumu dosya yapısına bağlı)
```

### 2.7 — CompanionGoalSelector urgency entegrasyonu

**Durum: Tamamlandı, TTL korumalı (2026-09-25).** Laya karar anında urgency, `is_urgent` sonucu ve timestamp kaydedilir. Companion needs snapshot'ına metadata olarak taşınır; YAML'deki `companion_goals.laya_urgency.freshness_s` süresi içinde yüksek urgency varsa snapshot güvenli `safety/pause_and_observe` adayına yükseltilir. Süresi geçmiş veya düşük urgency goal'u değiştirmez. GoalSelector mevcut GoalFormation/safety/capability katmanlarını kullanır; doğrudan donanım dispatch'i yoktur. Fresh ve expired durumlar için regresyon testleri eklendi.

**Dosya:** `modules/autonomy/services/companion_goal_selector.py`
**Strateji:** Dosyayı oku, goal scoring/ranking metodunu bul.

```python
# Goal scoring'de urgency'yi kullan:
# Eğer Laya urgency yüksekse, mevcut goal'u interrupt et
if hasattr(self, '_brain') and hasattr(self._brain, 'laya_engine'):
    laya = self._brain.laya_engine
    last_text = self._brain.state.get("last_speech_text", "")
    if last_text:
        dec = laya.decide(last_text)
        if dec and dec.urgency_score >= 1.5:
            # Mevcut goal'u ertele, acil goal'a geç
            pass
```

---

## FAZ 3: Agent Core Orkestrasyon Derinleştirme

### 3.1 — agent.py step() Fast-Path (LLM Atlama)

**Durum: Sınıflandırma hızlı yolu mevcut; direct-tool taslağı güvenlik nedeniyle uygulanmıyor.** Agent Laya kararını fast-path ve kısa LLM yanıt ayarı için kullanıyor. `suggested_tool` çağrı argümanlarını sağlamaz; Laya'nın `emergency_stop -> stop_follow` eşlemesi de gerçek `motor.stop` garantisi değildir. Acil sesli durdurma SpinalCord yolunda çalışır; Agent tool registry'ye sınıflandırma kararından doğrudan dispatch eklenmeyecek.

**Dosya:** `modules/agent_core/services/agent.py`
**Konum:** `step()` metodu, satır 149'daki `use_fast_path` kontrolünden sonra

**ÖNEMLİ:** Mevcut `_should_fast_path()` metodu `agent_context.py` veya `agent_turn.py`'da olabilir. Aramak için:
```
grep -rn "_should_fast_path" modules/agent_core/services/
```

Yapılacak: Laya `should_fast_path()` sonucunu mevcut fast_path kararına entegre et.

```python
# step() içinde, mevcut use_fast_path satırından ÖNCE:
laya_fast = False
laya_fast_decision = None
laya_eng = getattr(self, "laya_engine", None)
if laya_eng and getattr(laya_eng, "enabled", True):
    laya_fast, laya_fast_decision = laya_eng.should_fast_path(user_prompt)

# Mevcut use_fast_path kararını Laya ile birleştir:
use_fast_path = self._should_fast_path(user_prompt, native_tools=native_tools) or laya_fast

# Eğer Laya fast-path ise ve emergency ise:
if laya_fast and laya_fast_decision and laya_fast_decision.is_emergency:
    # LLM'yi tamamen atla, direkt tool çalıştır
    tool_name = laya_fast_decision.suggested_tool or "stop_follow"
    try:
        result = self.tool_registry.execute(tool_name, {})
        ack = laya_eng.get_fast_ack(session_language)
        self.speech_arbiter.enqueue(
            ack,
            priority=95,  # SAFETY priority
            category="safety",
            language=session_language,
        )
        return {
            "text": ack,
            "actions": [{"tool": tool_name, "args": {}, "result": result}],
            "route": [laya_fast_decision.target_module],
            "fast_path": True,
            "laya_decision": True,
            "trace_id": trace_id,
        }
    except Exception as exc:
        logger.warning("Laya fast-path execution failed: %s", exc)
        # Normal path'e düş
```

### 3.2 — tri_layer.py Dinamik Boost

**Dosya:** `modules/agent_core/services/tri_layer.py`
**Konum:** `route()` metodu, satır 415-417

**Mevcut kod:**
```python
for mod in laya_modules:
    if mod in self.profiles:
        scores[mod] = scores.get(mod, 0.0) + 10.0  # Sabit boost
```

**Yeni kod:**
```python
for mod in laya_modules:
    if mod in self.profiles:
        # Laya confidence'a göre dinamik boost (5.0 — 15.0 arası)
        laya_dec = getattr(self.laya_engine, '_last_decision', None)
        if laya_dec and hasattr(laya_dec, 'module_confidence'):
            boost = 5.0 + (laya_dec.module_confidence * 10.0)  # 0.0→5.0, 1.0→15.0
        else:
            boost = 10.0
        scores[mod] = scores.get(mod, 0.0) + boost
```

### 3.3 — agent_subagents.py Routing Birleştirme

**Dosya:** `modules/agent_core/services/agent_subagents.py`
**Konum:** `_route_subagents()` metodu (satır 30-46)
**Sorun:** Bu metod keyword matching yapıyor ama `self.router` (TriLayerRouter) da aynı şeyi yapıyor → **duplicate logic**.

**Yeni kod:**
```python
def _route_subagents(self, prompt: str) -> List[SubAgentProfile]:
    """Route subagents via TriLayerRouter (unified routing)."""
    # TriLayerRouter zaten keyword + Laya + semantic routing yapıyor
    module_names = self.router.route(prompt)
    self.last_routed_subagents = module_names
    
    selected: List[SubAgentProfile] = []
    for name in module_names:
        profile = self.subagent_profiles.get(name)
        if profile and getattr(profile, 'enabled', True):
            selected.append(profile)
    
    # Fallback
    if not selected and "agent_core" in self.subagent_profiles:
        fallback = self.subagent_profiles["agent_core"]
        if getattr(fallback, 'enabled', True):
            selected.append(fallback)
    
    return selected
```

### 3.4 — SpeechArbiter Laya Filler Priority

**Dosya:** `modules/agent_core/services/speech_arbiter.py`
**Konum:** `SpeechPriority` class'ından sonra (satır 49 civarı)

```python
class SpeechPriority:
    SAFETY = 95
    LAYA_FILLER = 75      # ← YENİ: Progress'ten yüksek, final'den yüksek
    FINAL_RESPONSE = 60
    PROGRESS = 30
    IDLE = 15
```

Yeni metod ekle (satır 216 civarı, `enqueue_safety`'den sonra):
```python
def enqueue_laya_filler(
    self,
    text: str,
    language: str = "",
    trace_id: str = "",
) -> Optional[str]:
    """Enqueue an ultra-low-latency Laya thinking filler."""
    return self.enqueue(
        text,
        priority=SpeechPriority.LAYA_FILLER,
        category="laya_filler",
        language=language,
        max_age_s=4.0,  # Kısa ömür — yeni final gelince expire olur
        trace_id=trace_id,
    )
```

### 3.5 — WorldState Laya State

**Dosya:** `modules/agent_core/services/world_state.py`
**Strateji:** Önce dosyayı oku, `update_state()` veya `set()` metodunu bul.

```python
# Yeni metod:
def update_laya_state(self, decision) -> None:
    """Store latest Laya System 1 decision in world state."""
    if decision is None:
        return
    self.update_state({
        "laya_last_target": getattr(decision, 'target_module', ''),
        "laya_last_urgency": float(getattr(decision, 'urgency_score', 0.0)),
        "laya_last_affect": getattr(decision, 'affective_event', 'neutral'),
        "laya_last_direct": bool(getattr(decision, 'is_direct_command', False)),
        "laya_last_ms": float(getattr(decision, 'inference_ms', 0.0)),
    })
```

### 3.6 — SensorLoop Urgency Boost

**Dosya:** `modules/agent_core/services/sensor_loop.py`
**Strateji:** Poll loop'u bul, urgency yüksekse interval'ı düşür.

```python
# _poll_loop veya _run içinde:
# Mevcut sleep/interval satırını bul ve şu mantığı ekle:
laya_engine = None
try:
    from modules.agent_core.services.laya_engine import LayaEngine
    laya_engine = LayaEngine.get_instance()
except Exception:
    pass

# Poll interval'ını belirlerken:
base_interval = 1.0 / self.poll_hz
if laya_engine and laya_engine._is_available:
    try:
        telemetry = laya_engine.get_telemetry()
        last = telemetry.get("last_decisions", [])
        if last and last[-1].get("urgency", 0) >= 1.5:
            base_interval = min(base_interval, 0.2)  # 5Hz'e çık
    except Exception:
        pass
```

### 3.7 — ActionArbiter Fast-Path Bypass

**Karar: Bypass eklenmiyor.** ActionArbiter quiet-hours, yetenek ve safety kontrollerinin sahibi. Acil motor durdurma bu action türlerinden değil spinal `motor.stop` reflex yolundan geçer. `move_head`/`stop_follow` için bu filtreleri atlamak acil durdurma eşdeğeri değildir ve safety katmanını gevşetirdi.

**Dosya:** `modules/agent_core/services/action_arbiter.py`
**Strateji:** Dosyayı oku, `check()` veya `approve()` metodunu bul.

```python
# Mevcut approval metoduna parametre ekle:
def approve(self, action_name, args, *, laya_emergency=False):
    # Emergency ise bazı safety check'leri atla
    if laya_emergency and action_name in {"stop_follow", "move_head"}:
        return True  # Acil dur komutları her zaman geçer
    
    # ... mevcut safety logic ...
```

### 3.8 — IdleBehavior Curiosity Trigger

**Durum: Sahiplik sınırı regression testiyle doğrulandı (2026-09-25).** `IdleBehaviorSystem` yalnızca nötr heartbeat ışığı üretir; Laya telemetry sorgusu, Agent semantic step veya hareket/vision kararı çalıştırmaz. `test_idle_heartbeat_does_not_run_laya_or_semantic_actions` bu sınırı korur. Curiosity tabanlı semantik tarama Autonomy idle planner kapsamındadır.

**Dosya:** `modules/agent_core/services/idle_behavior.py`
**Strateji:** Idle loop'u bul, curiosity yüksekse çevreye bakma tetikle.

```python
# Idle döngüsünde:
laya_engine = getattr(self._agent, 'laya_engine', None)
if laya_engine:
    telemetry = laya_engine.get_telemetry()
    # Son kararlardan curiosity seviyesini çıkar
    # Curiosity yüksekse → vision scan tetikle
```

---

## FAZ 4: VLM Bridge Entegrasyonu

### 4.1 — VisionProcessor detection → Laya affect

**Durum: Semantik etkiler mevcut owner katmanlarında karşılanıyor; Laya vision sınıflandırması yan etki üretmiyor.** `perception_context` kişi/sahip event'lerini ve yeni kişi appraisal'ını yönetir; `VisionContextNeedsBridge` kişi varlığı/yenilik sinyalini needs snapshot'a taşır; tehlike `visual_hazard` appraisal'ına gider. Gateway Laya handler bunları ek sınıflandırma ve state telemetrisi için alır. Aynı event için ikinci mood/need değişikliği eklenmedi; regression testi bunu korur.

**Dosya:** `modules/vlm_bridge/services/processor.py`
**Strateji:** `on_detection()` veya detection callback'ini bul.

```python
# Yeni kişi tespit edildiğinde:
try:
    from modules.agent_core.services.laya_engine import LayaEngine
    laya = LayaEngine.get_instance()
    if laya.is_available:
        # Kişi tespiti → social need satisfy
        # Bu kısım processor'ın yapısına bağlı
        pass
except Exception:
    pass
```

### 4.2 — VisionEventBus Laya subscriber

**Durum: Tamamlandı.** Gateway bridge event bus'a abone olup vision event'lerini worker üzerinden Autonomy Laya handler'ına aktarır; güven eşikleri/cooldown uygulanır.

**Dosya:** `modules/vlm_bridge/services/vision_event_bus.py`
**Strateji:** `subscribe()` veya `register_handler()` metodunu bul.

```python
# Laya subscriber ekle:
def _laya_vision_handler(event_type: str, payload: dict):
    """Forward vision events to Laya affective pipeline."""
    try:
        from modules.agent_core.services.laya_engine import LayaEngine
        laya = LayaEngine.get_instance()
        if not laya.is_available:
            return
        
        if event_type == "person_detected":
            # Kişi → social event
            pass
        elif event_type == "owner_detected":
            # Sahip → user_praise benzeri
            pass
        elif event_type == "hazard_detected":
            # Tehlike → urgency artır
            pass
    except Exception:
        pass
```

### 4.3 — VisualContext Laya kısa özet

**Durum: Tamamlandı.** VisualContext kısa sahne özetini sunar; Agent ve event yolları bu özeti Laya kararına bağlar.

**Dosya:** `modules/vlm_bridge/services/visual_context.py`

```python
def get_laya_context(self) -> str:
    """Returns a brief scene summary for Laya System 1 input (max 100 chars)."""
    # Mevcut context'ten kısa bir özet oluştur
    ctx = self.get_context()  # veya benzeri mevcut metod
    if not ctx:
        return ""
    # Kısa özet: "2 kişi, masa, laptop görünüyor"
    objects = ctx.get("objects", [])[:5]
    people_count = ctx.get("people_count", 0)
    parts = []
    if people_count:
        parts.append(f"{people_count} kişi")
    for obj in objects:
        parts.append(str(obj.get("label", "")))
    return ", ".join(parts)[:100]
```

### 4.4 — FaceEmotion → Laya affect

**Durum: Tamamlandı.** Confidence/cooldown korumalı yüz event'i Laya tarafından sınıflandırılır; yalnızca yüksek güvenli praise/rude sonucu MoodManager'ı değiştirir.

**Dosya:** `modules/vlm_bridge/services/face_emotion.py`
**Strateji:** Yüz duygusu tespit eden metodu bul, Laya'ya event gönder.

```python
# Yüz duygusu tespit edildiğinde:
# Eğer kullanıcının yüzü "angry" ise → robot bunu hissetmeli
detected_emotion = ...  # mevcut tespit sonucu
if detected_emotion in {"angry", "disgusted"}:
    # MoodManager'a bildir
    try:
        # Bu event AutonomyBrain üzerinden mood'a ulaşmalı
        pass
    except Exception:
        pass
```

---

## FAZ 5: Ses Pipeline

### 5.1 — AgentStreaming mood-aware tone

**Durum: Tamamlandı (2026-09-24).** `AutonomyBrain` yerel `MoodManager` referansını `AgentOrchestrator`'a verir. Her `step()` ve `step_event()` başında tek bir tone snapshot'ı alınır; streaming cümleleri `SpeechArbiter.enqueue_final_chunk()` üzerinden bu tonu TTS'e taşır. Mood yöneticisi bulunamaz veya hata verirse `None` ile mevcut varsayılan ton korunur. Ağ çağrısı/cümle başına mood okuması eklenmedi.

**Dosya:** `modules/agent_core/services/agent_streaming.py`
**Konum:** `_stream_turn_sentence_by_sentence()` metodu

```python
# Gerçek uygulama AgentOrchestrator.step()/step_event() içinde:
# MoodManager.get_speech_tone() bir kez alınır ve enqueue_final_chunk(tone=...)
# ile bu turdaki her stream cümlesine aktarılır.
```

### 5.2 — xSpeakService Laya filler endpoint

**Durum: Mevcut güvenli pipeline ile karşılandı; ayrı endpoint eklenmiyor (2026-09-24).** `AgentOrchestrator.step()` Laya filler metnini `ProgressManager.emit_ack()`'e verir; bu metin `SpeechArbiter.enqueue_laya_filler()` üzerinden TTL/öncelik kurallarıyla normal `speak_preferred` TTS sınırına ulaşır. `/speak/laya_filler` endpoint'i kuyruğu atlayıp konuşma önceliği, cooldown ve barge-in koordinasyonunu bozardı; bu nedenle doğrudan endpoint taslağı uygulanmadı. Akış regression testi `test_progress_routes_laya_ack_through_priority_queue` ile korunuyor.

**Dosya:** `modules/voice/speak/xSpeakService.py`
**Karar:** FastAPI router'a yeni endpoint ekleme; agent progress/speech arbiter zinciri bu işi zaten yapar.

```python
@router.post("/speak/laya_filler")
async def laya_filler(language: str = "tr"):
    """Ultra-low-latency filler speech triggered by Laya System 1."""
    from modules.agent_core.services.laya_engine import LayaEngine
    laya = LayaEngine.get_instance()
    text = laya.get_instant_filler(language)
    # Mevcut speak mekanizmasıyla seslendir
    # ...
    return {"text": text, "status": "ok"}
```

### 5.3 — AudioRouter urgency barge-in

**Durum: Emergency barge-in mevcut ve entegrasyon testiyle doğrulandı (2026-09-25).** Sesli konuşma Brain `VocalMixin` yolunda Laya yalnızca zaten yüklüyse emergency sınıflandırması yapar; `BargeInController` bu urgency sinyaliyle tek kelimelik acil ifadede konuşmayı keser. AudioRouter'a ikinci bir urgency sahibi eklenmedi. `test_laya_emergency_reaches_brain_barge_in_controller` Laya → controller → stop zincirini doğrular.

**Dosya:** `modules/voice/audio_router.py`
**Strateji:** Barge-in (konuşma kesme) mekanizmasını bul, urgency yüksekse otomatik kes.

### 5.4 — BargeIn urgency threshold

**Durum: Mevcut Laya emergency threshold'u kullanılıyor (2026-09-25).** Threshold LayaEngine config'indeki `emergency_threshold` üzerinden `is_emergency_decision()` ile belirlenir; bağımsız ve çakışan bir BargeIn threshold'u eklenmez. Cooldown ve wakeword kuralları korunur.

**Dosya:** `modules/autonomy/services/barge_in.py`
**Strateji:** Threshold'u Laya urgency'ye göre dinamik yap.

---

## FAZ 6: Tool Execution & Progress

### 6.1 — ToolRegistry Laya hint

**Durum: Tamamlandı (2026-09-24), teşhis amaçlı.** Agent, native LLM tool çağrısında aynı turdaki Laya `suggested_tool` değerini opsiyonel `laya_hint` olarak iletir. Registry bunu yalnızca başarılı tool status telemetrisine ve eşleşme boolean'ına ekler; tool seçimini/argümanlarını değiştirmez, yetki vermez ve yeni tool çalıştırmaz. Böylece Laya önerisi ile modelin seçimi gözlemlenebilir kalır; backward compat nedeniyle recovery callback'lerinin mevcut iki argümanlı çağrısı çalışmaya devam eder.

**Dosya:** `modules/agent_core/services/tools/tool_registry.py`, `modules/agent_core/services/agent_turn.py`
**Güvenlik sınırı:** `laya_hint` yalnızca telemetri içindir; dispatch girdisi değildir.

### 6.2 — ProgressManager TTFT metrik

**Durum: Tamamlandı, metrik doğru katmana alındı (2026-09-24).** Laya çıkarımı Agent girişinde `latency_trace`'e ayrı `laya.inference` olayı olarak yazılır (inference_ms, target_module, urgency). LLM stream TTFT'si model yanıtının ilk token süresidir; Laya inference süresini bu sayıya eklemek farklı iki ölçümü karıştıracağından yapılmıyor. Event tabanlı Agent çağrılarında da aynı işaretleme kullanılır; Laya karar yoksa event yazılmaz.

**Dosya:** `modules/agent_core/services/agent.py`, `modules/common/latency_trace.py`
**Karar:** Laya inference latency ayrı trace event'idir; model TTFT metriğine eklenmez.

### 6.3 — ToolExecutionArbiter fast-path bypass

**Karar: Uygulanmıyor; emergency refleksi bu arbiter'dan geçmiyor (2026-09-24).** ToolExecutionArbiter ortak VLM/head/light kaynaklarını çakışmadan kilitler. Bu kilidi Laya sınıflandırmasıyla bypass etmek aynı fiziksel/vision kaynağında eşzamanlı komutlara izin verir. Acil motor durdurma `SpinalCordReflex.observe_voice_emergency()` üzerinden doğrudan `motor.stop` olayına gider; normal tool arbiter'ını gevşetmez. Fast-path yalnızca LLM katmanını atlayabilir, kaynak/safety arbiter'larını değil.

**Dosya:** `modules/agent_core/services/tool_execution_arbiter.py`

### 6.4 — SafetyFilter emergency elevated

**Karar: Generic SafetyFilter'a elevation eklenmiyor (2026-09-24).** Bu filtre agent action argümanlarını sınırlar/quiet-hours politikasını uygular; spinal cord emergency stop ayrı runtime sahibi altında. Genel emergency override eklemek quiet-hours veya hardware limit kontrollerini de yanlışlıkla aşma riski taşır ve mevcut reflex yoluna katkı sağlamaz. Laya emergency confidence/threshold kontrolü ve spinal stop yolu ayrı testlerle korunur.

**Dosya:** `modules/agent_core/services/safety_filter.py`

---

## FAZ 7: Test Suite

### 7.1 — test_laya_engine.py genişlet

**Durum: Tamamlandı (2026-09-25).** Context, telemetry ve mood-aware filler testleri zaten vardı; ek olarak emergency, güvenilir direct hardware ve normal conversation fast-path ayrımı test edildi.
Mevcut testlere ekle:
- `test_decide_with_context()`
- `test_get_telemetry()`
- `test_get_filler_with_affect()`

### 7.2 — test_laya_fast_path.py oluştur

**Durum: Mevcut Laya engine test dosyasında tamamlandı.** Aynı davranış için ayrı dosya açmak yerine `test_laya_engine.py` içinde üç path koşulu kapsandı. “Fast-path” burada LLM karar yolunu seçer; fiziksel tool dispatch yetkisi vermez.
```python
def test_emergency_fast_path():
    """Emergency command → LLM bypass, direkt tool execution."""
    
def test_direct_command_fast_path():
    """Direct hardware command → fast-path execution."""
    
def test_conversation_no_fast_path():
    """Normal sohbet → LLM path (fast-path olmamalı)."""
```

### 7.3 — test_laya_brain_integration.py oluştur

**Durum: Tamamlandı (2026-09-25).** Yeni test dosyası emergency kararın SpinalCordReflex üzerinden `motor.stop` üretmesini ve normal sohbet kararının motoru durdurmamasını doğrular. BrainInit'in Laya singleton attachment'ı `brain_init.py` içinde mevcut.
```python
def test_brain_has_laya_engine():
    """AutonomyBrain laya_engine attribute'una sahip olmalı."""
    
def test_laya_emergency_triggers_spinal_cord():
    """Laya emergency → SpinalCord reflex tetiklenmeli."""
```

### 7.4 — test_laya_vlm_bridge.py oluştur

**Durum: Mevcut `tests/modules/vlm_bridge/test_laya_vision_events.py` ve `tests/modules/autonomy/test_laya_vision_event.py` ile tamamlandı.** Confidence/cooldown event yayını ve autonomy Laya/mood subscriber davranışı kapsanıyor; yinelenen test dosyaları eklenmedi.
```python
def test_vision_event_laya_subscriber():
    """Vision event → Laya affective pipeline çalışmalı."""
```

### 7.5 — test_laya_speech_flow.py oluştur

**Durum: Mevcut speech boundary testlerine genişletilerek tamamlandı.** Progress ACK'nin Laya filler kuyruğuna girdiği ve filler'ın final yanıt öncesinde seçildiği doğrulanıyor.
```python
def test_filler_before_llm_response():
    """Laya filler, LLM yanıtından önce seslenmeli."""
```

---

## HIZLI REFERANS: Önemli Dosya Konumları

```
Proje kökü: c:\Users\emohi\Desktop\Project SentryBOT V5\

LAYA ÇEKIRDEĞI:
  modules/agent_core/services/laya_engine.py     ← LayaEngine + LayaDecision
  modules/agent_core/services/tri_layer.py        ← TriLayerRouter + SubAgentProfile
  
ORKESTRASYON:
  modules/agent_core/services/agent.py            ← AgentOrchestrator.step()
  modules/agent_core/services/agent_context.py    ← AgentContextMixin (init)
  modules/agent_core/services/agent_turn.py       ← AgentTurnMixin (LLM loop)
  modules/agent_core/services/agent_streaming.py  ← Clause streaming
  modules/agent_core/services/agent_subagents.py  ← Sub-agent delegation
  
BEYİN:
  modules/autonomy/services/brain.py              ← AutonomyBrain (sense/think loop)
  modules/autonomy/services/brain_init.py          ← Component initialization
  modules/autonomy/services/mood.py               ← MoodManager
  modules/autonomy/services/system1_reflex.py     ← DEPRECATED → LayaEngine proxy
  modules/autonomy/services/spinal_cord_reflex.py ← Emergency hardware reflex
  modules/autonomy/services/behavior_composer.py  ← Behavior chain selection
  
SES:
  modules/agent_core/services/speech_arbiter.py   ← Priority speech queue
  modules/voice/speak/xSpeakService.py            ← TTS service
  modules/voice/audio_router.py                   ← Audio capture routing
  
GÖRÜNTÜ:
  modules/vlm_bridge/services/processor.py        ← Vision main processor
  modules/vlm_bridge/services/vision_event_bus.py ← Vision event pub/sub
  modules/vlm_bridge/services/visual_context.py   ← Scene context
  modules/vlm_bridge/services/face_emotion.py     ← Face emotion detection
  
CONFIG:
  config/agent.yaml                                ← Ana yapılandırma

TESTLER:
  tests/modules/agent_core/test_laya_engine.py    ← Mevcut Laya testleri
```

---

## KRİTİK KURALLAR (HER FAZDA UYULMALI)

1. **Singleton:** `LayaEngine.get_instance(config)` — yeni instance oluşturma
2. **Backward compat:** Mevcut API imzalarını değiştirme, yeni parametre eklerken `default` ver
3. **Thread safety:** `with self._lock:` kullan (MoodManager, SpeechArbiter zaten RLock kullanıyor)
4. **Config:** Her yeni ayar `config/agent.yaml`'a eklenmeli, hardcode yasak
5. **Test:** Her faz sonunda `pytest tests/ -x -q` çalıştır
6. **Silme yok:** Mevcut kodu silme, deprecate et veya proxy yap
7. **Import:** Lazy import kullan (`try: ... except ImportError:`) — modül bağımsızlığı
8. **Logging:** `logger = logging.getLogger("modül_adı")` ile logla
9. **Error handling:** Laya hataları asla ana akışı bozmamalı — `try/except` ile sar
> **2026-09-27 — ses komutu parser ölçümü:** Evaluator-only deterministik literal parser, 30 örnekli intent dev setinde 5/5 komutu yakaladı ve 0 FP verdi. Yeni, ayrık 30 örnekli audio holdout tek sefer ölçüldü: TP 8, FP 4, FN 0, TN 18; accuracy 0.867, precision 0.667, recall 1.000. Konuşma/soru bağlamındaki command-like fiiller yanlış pozitif ürettiği için parser intent/dispatch kapısı olarak reddedildi. Holdout tüketildi; bu veride tuning yapılmamalı. CLI modu Laya/Torch yüklemeden çalışır ve hiçbir tool/hardware çağrısı yapmaz. Production davranışı ve `action_proposals.enabled: false` değişmedi. Sıradaki iş: bağımsız, daha geniş ve haricen gözden geçirilmiş intent/safety korpusu hazırlamak; target/direct/emergency/effect eşiklerini orada doğrulamak. Ardından typed proposal validator ve sıfır çağrı garantili simüle dispatcher; en son cihaz üstü kabul testi.

> **2026-09-27 — saf request-bound validator:** `laya_action_contract.py` içine request ID bağlama ve exact-schema validator eklendi. Validator current request eşleşmesini, yalnız `set_lights` allowlist'ini, exact schema/argument key'lerini, enum değerlerini ve config confidence eşiğini kontrol edip bool döndürüyor; malformed/extra/stale/low-confidence öneriyi reddediyor. Regression testleri eklendi. Bu validator ToolRegistry/dispatcher'a bağlanmadı; proposal config kapalı. Bir sonraki kod adımı dispatcher eklemek değil, mevcut request lifecycle'da stabil request ID üretimini izleyip bu sınırı test etmek; bundan sonra yalnız simülasyon dispatcher'ı sıfır çağrı garantisiyle ele almak. Haricen gözden geçirilmiş daha geniş intent/safety dataseti hâlâ açık kapı.

> **Request lifecycle takibi:** API `trace_id` değeri çağıran taraftan gelebiliyor; bu nedenle güvenlik bağı olarak kullanılmadı. Agent, kabul edilmiş `step()` başına ayrı UUID üretiyor, Laya inert proposal'ına bağlıyor ve turn sonunda temizliyor. Regression testi bu ayrımı doğruluyor. Request binding tamamlandı; `step_event()` / native tool akışında Laya proposal yetkisi bulunmuyor, hiçbir dispatcher bağlantısı eklenmedi. Sıradaki kod kapısı: simülasyon-only validator/dispatcher test seam'i tasarlamak ve reddedilen girdilerde execute çağrısının sıfır kaldığını kanıtlamak; bunu ancak independent intent değerlendirme ve tool-owner safety kontrolleri kapalı değilken ele al.

> **2026-09-27 — tool-owner safety incelemesi:** Mevcut `set_lights` compatibility tool'u `queue_action("lights", ...)` ile agent-core `ActionArbiter`'a gidiyor; `ActionSafetyFilter`'da lights-specific capability approval yok. Kayıtlı handler expression-light lease alıp Autonomy client'ını çağırıyor, ancak Autonomy `CapabilityExecutor`'ına girmiyor. ToolRegistry execution arbiter'ı ayrı bir concurrency sınırı ve runtime-owner capability kararı değil. Bu nedenle execute çağıran bir dispatcher veya onu taklit eden test seam'i eklenmedi; zorunlu owner safety gate'ini kanıtlayamazdı. Sıradaki gerçek iş, Autonomy tarafında Laya-origin lights isteği için açık capability approval/deny yolu kurup reddin handler/hardware çağrısını sıfır tuttuğunu test etmek; ondan sonra dispatcher tasarlanabilir. Intent/safety dataseti ayrıca dış gözden geçirme bekliyor. `action_proposals.enabled: false` sürüyor.
