# Laya System 1 Entegrasyonu — YAPILAN İŞLER

> **Son güncelleme:** 2026-09-27
> **Durum:** Dispatch kapalı güvenli entegrasyon ve doğrulama fazı tamamlandı. Bu, donanıma aksiyon rollout'unun tamamlandığı anlamına gelmez. `action_proposals.enabled: false` kalır; Autonomy capability gate, bağımsız veri kabulü, simülasyon dispatch güvenliği, emergency-stop kontratı ve Raspberry Pi kabulü tamamlanana kadar eylem açılmayacak.
> **Son test:** `pytest tests -x -q` — **970 passed in 43.98s**. Ayrıca py_compile ve git diff --check temiz.
> **Kullanım:** Bu dosya yapılanların kayıt defteri; kalan işleri ve sırayı `.sentrybot/laya_integration_todo.md` başındaki güncel durum bloğu belirler.

---

## 1. Laya Model İndirme Aracı

**Dosya:** `tools/download_laya_model.py`
**Durum:** ✅ Tamamlandı, çalışıyor
**Ne yapıyor:** Hugging Face'den `convaiinnovations/laya` modelini `~/.cache/huggingface/` altına indirir.
**Test:** `python tools/download_laya_model.py` ile çalıştırılabilir.

---

## 2. LayaEngine — System 1 Nöral Karar Motoru

**Dosya:** `modules/agent_core/services/laya_engine.py` (366 satır)
**Durum:** ✅ Oluşturuldu, çalışıyor

### Sınıf: `LayaDecision` (dataclass, satır 42-57)
Laya çıkarımının sonucu. Alanlar:
- `target_module: str` — hedef modül (neopixel, arduino_serial, emergency_stop, speak, camera, system2_chat)
- `module_confidence: float` — modül güven skoru
- `is_direct_command: bool` — doğrudan donanım komutu mu?
- `direct_confidence: float`
- `affective_event: str` — user_praise, user_rude, neutral
- `affect_confidence: float`
- `urgency_score: float` — 0-3 arası aciliyet
- `urgency_confidence: float`
- `inference_ms: float` — çıkarım süresi
- `suggested_tool: Optional[str]` — önerilen tool adı
- `is_emergency` property — urgency >= 2.0 veya emergency_stop

### Sınıf: `LayaEngine` (satır 64-366)
- **Singleton pattern** — `get_instance(config)` ile tek instance
- **`SENTRYBOT_QUESTIONS`** (satır 75-115) — Laya'ya sorulacak 4 soru tanımı:
  1. `target_module` — 6 seçenekli modül sınıflandırma
  2. `is_direct_command` — direct_action vs conversation
  3. `affective_event` — user_praise, user_rude, neutral
  4. `urgency` — 0-3 skor (sakin → son derece acil)
- **`MODULE_TOOL_MAP`** (satır 117-123) — modül → tool eşleme
- **`_ensure_loaded()`** (satır 185-229) — Lazy model loading, `import laya` → `laya.load()`
- **`_find_cached_snapshot()`** (satır 162-183) — HF cache'de model arama
- **`decide(text)`** (satır 235-285) — Ana çıkarım metodu, `LayaDecision` döner
- **`route(user_prompt, available_modules)`** (satır 287-313) — Modül yönlendirme
- **`should_fast_path(user_prompt)`** (satır 315-328) — Fast-path kararı
- **`get_instant_filler(language)`** (satır 330-335) — Düşünme ara sesi
- **`get_fast_ack(language)`** (satır 337-342) — Hızlı onay sesi
- **`get_affective_reaction(affect)`** (satır 344-365) — OLED yüz + LED renk

### Config okuması:
```python
# config["tri_layer"]["laya"] altından okur:
# enabled, confidence_threshold, model_path
```

---

## 3. TriLayerRouter Güncellemesi

**Dosya:** `modules/agent_core/services/tri_layer.py`
**Durum:** ✅ Güncellendi

### Değişiklikler:
- **`__init__` parametresi** (satır 293): `laya_engine: Any = None` eklendi
- **`route()` metodu** (satır 398-424): Laya nöral routing eklendi:
  ```python
  # satır 403-408: Laya modüllerini al
  if self.laya_engine is not None and getattr(self.laya_engine, "enabled", True):
      laya_modules = self.laya_engine.route(user_prompt, list(self.profiles.keys()))
  
  # satır 415-417: Laya modüllerine +10.0 sabit boost
  for mod in laya_modules:
      if mod in self.profiles:
          scores[mod] = scores.get(mod, 0.0) + 10.0
  ```

---

## 4. AgentContextMixin — Laya Başlatma

**Dosya:** `modules/agent_core/services/agent_context.py`
**Durum:** ✅ Güncellendi

### Değişiklikler:
- **`_init_tri_layer()` metodu** (satır 307-344):
  ```python
  # satır 318-320:
  from .laya_engine import LayaEngine
  self.laya_engine = LayaEngine.get_instance(config)
  # Router'a laya_engine parametre olarak verildi:
  self.router = TriLayerRouter(..., laya_engine=self.laya_engine)
  ```

---

## 5. AgentOrchestrator — Laya step() Entegrasyonu

**Dosya:** `modules/agent_core/services/agent.py`
**Durum:** ✅ Kısmi entegrasyon (MVP seviyesinde)

### Değişiklikler (satır 149-166):
```python
# step() içinde Laya kullanımı:
laya_eng = getattr(self, "laya_engine", None)
if laya_eng and getattr(laya_eng, "enabled", True):
    # 1. Filler üret (LLM beklerken)
    custom_ack = laya_eng.get_instant_filler(language=session_language)
    # 2. Affective event → autonomy expression
    laya_dec = laya_eng.decide(user_prompt)
    if laya_dec and laya_dec.affective_event in {"user_praise", "user_rude"}:
        reaction = laya_eng.get_affective_reaction(laya_dec.affective_event)
        autonomy_client.set_expression_event("agent.affect", reaction)
```

**EKSİK:** Fast-path (LLM atlama), urgency gate, tool hint, world state update — bunlar Faz 3'te yapılacak.

---

## 6. AgentStreaming — Clause-Level Streaming

**Dosya:** `modules/agent_core/services/agent_streaming.py`
**Durum:** ✅ Güncellendi

### Değişiklikler (satır 32-33, 92-104):
```python
_FIRST_CLAUSE_SPLIT_RE: Optional[re.Pattern] = None
# ...
# satır 92-93: Ultra düşük gecikmeli ilk cümlecik bölme
AgentStreamingMixin._FIRST_CLAUSE_SPLIT_RE = re.compile(r"([,;:—–\n]+|[.!?…]+)")

# satır 96-104: İlk chunk'ta virgül/bağlaçtan böl
if is_first_chunk:
    words = buffer.split()
    if len(words) >= 2 or len(buffer) >= 12:
        parts = _FIRST_CLAUSE_SPLIT_RE.split(buffer)
        if len(parts) > 1:
            first_clause = (parts[0] + parts[1]).strip()
            ...
```

---

## 7. MoodManager — Affective Event İşleme

**Dosya:** `modules/autonomy/services/mood.py`
**Durum:** ✅ Kısmi güncelleme

### Değişiklikler (satır 129-141):
```python
def apply_affective_event(self, event_name: str) -> str:
    event = str(event_name or "").strip().lower()
    with self._lock:
        if event == "user_praise":
            self.modify("happiness", 25)
            self.modify("anger", -15)
            self.modify("social", 20)
        elif event == "user_rude":
            self.modify("anger", 30)
            self.modify("happiness", -25)
            self.modify("fear", 10)
    return self.get_dominant_emotion()
```

**EKSİK:** `apply_laya_decision(decision: LayaDecision)` — tam karar nesnesi alması, urgency'yi de işlemesi gerekiyor. Faz 2'de yapılacak.

---

## 8. Test Dosyaları

### `tests/modules/agent_core/test_laya_engine.py`
**Durum:** ✅ Oluşturuldu
- LayaDecision dataclass testleri
- LayaEngine singleton test
- `route()` ve `should_fast_path()` testleri
- Mock-based, `laya` kütüphanesi gerekmez

### `tools/test_sentrybot_laya_live.py`
**Durum:** ✅ Oluşturuldu
- Canlı model testi (gerçek Laya modeli gerekir)
- Raspberry Pi üzerinde çalıştırılmak üzere tasarlandı

---

## 9. Config Durumu

**Dosya:** `config/agent.yaml`
**Durum:** ⚠️ Laya section henüz eklenmedi

Mevcut yapıda Laya config'i `tri_layer.laya` altından okunuyor (satır 150-154 laya_engine.py):
```python
tri_cfg = cfg.get("tri_layer", {})
laya_cfg = tri_cfg.get("laya", {})
enabled = bool(laya_cfg.get("enabled", True))
threshold = float(laya_cfg.get("confidence_threshold", 0.60))
model_path = laya_cfg.get("model_path")
```

**Config'de şu an bu key yok** — default değerler kullanılıyor. Faz 1'de eklenecek.

---

## 10. İlk Taslakta Dokunulmamış Olarak İşaretlenen Dosyalar

> Bu tablo ilk entegrasyon taslağının tarihsel durumudur; 2026-09-24 devam notu güncel durumu belirtir.

Aşağıdaki dosyalar **HİÇ değiştirilmedi** ve Faz 1-7'de değiştirilecek:

| Dosya | Faz |
|-------|-----|
| `modules/autonomy/services/brain_init.py` | 2 |
| `modules/autonomy/services/brain.py` | 2 |
| `modules/autonomy/services/system1_reflex.py` | 2 |

## 11. 2026-09-24 Devam Oturumu

- Config, `decide_with_context`, telemetri, mood-aware filler, mood delta ve spinal cord voice emergency desteği önceki çalışma ağacında zaten uygulanmıştı; Faz 0 diye belgelendirilmiş durum güncellendi.
- `TriLayerRouter` Laya güven skoruna göre dinamik ağırlık veriyor (5–15).
- `AgentSubagentsMixin._route_subagents()` artık aynı `TriLayerRouter` sonucunu kullanıyor; keyword tabanlı ikinci routing yolu kaldırıldı.
- Agent turn fast-path kontrolünde üretilen Laya kararı aynı turdaki affective tepki için tekrar kullanılıyor; gereksiz ikinci inference önlendi.
- `LayaDecision.is_emergency` artık engine config'indeki `emergency_threshold` değerini taşıyor; varsayılan 2.0 ve eski kurucularla uyumlu.
- `WorldState.update_laya_state()` son kararı thread-safe sensör state'ine yazar; agent turu bu güncellemeyi yapar.
- VisualContextCache sahneyi kişi/nesne/tehlike özeti olarak Laya için kısaltabilir.
- Laya filler kuyruğu progress ve final yanıt önceliğinin üstünde, safety önceliğinin altında ve 4 saniyelik ömre sahip; ProgressManager bunu destekleyen arbiter'larda kullanıyor.
- SensorFeedbackLoop yakın zamanda yüksek urgency görülünce yapılandırılmış süre boyunca daha sık tick eder. `urgency.sensor_boost_hold_s` eklendi; donanım kanalının kendi polling bütçeleri değişmeden kalıyor.
- Konuşma sürerken Laya acil karar verirse, BargeInController tek kelimelik acil ifadeyle TTS'i kesebilir; var olan cooldown ve wakeword davranışı korunur. Model önceden yüklenmemişse barge-in yolu yeni model yükleyip gecikme yaratmaz.
- Agent fast-path kararı ve affective tepki, `WorldState`'teki güncel sensör ve kısa VLM sahne özetiyle `decide_with_context()` üzerinden çalışır. `should_fast_path()` yeni parametreleri varsayılanlı aldığı için önceki çağrılarla uyumludur; eski adapter'lar için fallback korunur.
- VLM Bridge `face_emotion` event'i yalnızca yapılandırılmış confidence eşiği üstünde yayınlar; aynı kişi/duygu kombinasyonu cooldown boyunca bastırılır. Gateway event bridge'i bu sinyali mevcut agent-event yoluna iletir ve autonomy Brain'e bağlar.
- Autonomy Brain, yüz duygu event'ini Laya'ya verir; yalnızca Laya'nın `user_praise`/`user_rude` sınıfı da yapılandırılmış affect confidence eşiğini geçtiğinde mood değişir. Düşük güven, nötr, bilinmeyen veya tekrar event'leri mood'u değiştirmez. Bu yol Laya henüz yüklenmemişse yüklemeyi tetiklemez.
- Gateway VLM event bridge'i `owner_seen`, `new_person`, `hazard_detected` ve `scene_changed` olaylarını da worker üzerinden Laya vision handler'ına aktarır. Laya karar özeti state'e yazılır; bu olaylar tek başına motor/actuator veya mood değişikliği yapmaz. Olay/kişi başına cooldown tekrarları bastırır.
- Autonomy görsel tehlikeyi artık `loud_noise` olarak değil ayrı `visual_hazard` appraisal olayı olarak değerlendirir; YAML kuralı fear/energy/curiosity tepkisini tanımlar. VLM event bridge tehlike için actuator tetiklemez; mevcut autonomy appraisal sahibi kalır.
- Regression testleri eklendi. Önceki hedefli test kümesi **52 passed**; son eklerle genişletilen test kümesi de **52 passed** verdi.
- Tam `pytest tests/ -x -q` denemesi, `pydantic_core._pydantic_core` binary modülü yüklenemediğinden test toplamaya başlarken durdu. `.venv` launcher'ı başka makinedeki Python yoluna işaret ediyor; hazır runtime Python'ına `.venv/Lib/site-packages` bağlamak pure-Python testleri çalıştırdı ama native modül uyumsuzluğunu çözmedi.

### Devam eden maddeler / güvenlik notu

- Faz 3.1'de taslaklanan sınıflandırma tabanlı doğrudan tool çalıştırması eklenmedi: `suggested_tool` argümanları içermez ve emergency için `stop_follow` eşlemesi robotu güvenli biçimde durdurmayı garanti etmez. Sesli emergency zaten SpinalCord üzerinden `motor.stop` ile ele alınıyor. Agent seviyesindeki Laya fast-path LLM yolunu kısaltır.
- Faz 3.4'ün Laya filler önceliği, 3.5 WorldState özeti ve Faz 4.3 sahne özeti tamamlandı. Faz 3.6 sensör urgency tick'i de uygulandı.
- Faz 3.7 ActionArbiter bypass uygulanmadı; safety kontrolleri korunur, emergency stop spinal reflex sahibindedir. Faz 4.1 kişi/tehlike semantiği mevcut perception/needs/appraisal sahiplerine bağlıdır; vision Laya handler ikinci bir mood etkisi üretmez. Faz 3.8 idle heartbeat kararı aşağıda kayıtlıdır. Faz 5.1–7 tamamlanma kayıtları da aşağıdadır.
- Fast-path + sahne bağlamı test kümesi **46 passed** verdi; Python derlemesi ve `git diff --check` temiz. Tam test paketi için önceki nottaki native `pydantic_core` ortam engeli sürüyor.
- VLM yüz-duygu event zinciri için hedefli testler **47 passed** verdi.
- Genişletilmiş VLM event ve ilgili regression kümesi **41 passed** verdi; derleme ve diff kontrolleri temiz.
- Görsel tehlike appraisal ve VLM/autonomy regression kümesi **21 passed** verdi.
- Faz 5.1 mood-aware streaming tamamlandı: AutonomyBrain, yerel MoodManager'ı AgentOrchestrator'a bağlar; step/step_event tek mood tone snapshot'ını tüm cümle chunk'larına geçirir. Mood okuması başarısızsa eski nötr/varsayılan TTS yolu korunur.
- Faz 5.2 endpoint taslağı ayrı bir `/speak/laya_filler` API'si eklemeden tamamlandı: Laya ACK zaten ProgressManager → öncelik/TTL kontrollü SpeechArbiter → mevcut speak TTS sınırından geçiyor. Endpoint pipeline'ı bypass edip koordinasyonu bozacağından gereksiz. Yol için regression testi eklendi.
- Faz 6.1 Laya tool hint telemetrisi tamamlandı: native tool dispatch mevcut LLM kararını uygular; Laya'nın önerdiği tool yalnızca successful status event'inde eşleşme telemetrisi olarak görünür, çalıştırma yetkisi sağlamaz.
- Faz 6.2 Laya inference süresi `laya.inference` latency trace event'i olarak kaydedilir. LLM TTFT ile farklı ölçüm olduğu için ayrı tutulur; event bu Agent turunda karar oluştuysa eklenir.
- Faz 6.3/6.4 taslakları güvenli mimari kararıyla uygulanmadı: ToolExecutionArbiter kaynak kilitlerini korur; acil durdurma spinal cord üzerinden çalışır ve genel SafetyFilter override'ı eklenmez. Bu separation, Laya emergency reflex ve barge-in testleriyle mevcut durumda doğrulanmıştır.
- Faz 7 kapsamı tamamlandı: Laya engine context/telemetry/mood filler testleri zaten vardı; emergency/direct/conversation fast-path ayrımı eklendi. Yeni autonomy integration testleri emergency spinal motor stop ve non-emergency no-stop davranışlarını doğrular. VLM event testleri mevcut dosyalarda yeterli olduğundan tekrar üretilmedi. Speech ACK→filler queue ve filler-before-final seçimi test edildi.
- 2026-09-25 Faz 7 ve ilişkili regression kümesi: **61 passed**; ilgili yeni testler `py_compile` ile derlendi, `git diff --check` temiz. Tam test paketi bu turda çalıştırılmadı; bilinen native `pydantic_core._pydantic_core` toplama engeli önceki oturum notlarında kayıtlı.
- 2026-09-25 açık taslak denetimi: 2.6 mevcut MoodManager→`_speak_with_mood` zinciriyle karşılandı ve gerçek mood tone regresyon testi eklendi; ikinci composer karar katmanı eklenmedi. 3.8 için heartbeat'in Laya/semantic action çalıştırmadığını doğrulayan sahiplik regresyon testi eklendi; semantik idle planı Autonomy sahibinde kalır. 2.7 freshness korumalı semantic safety goal overlay olarak tamamlandı.
- Faz 2.7 regression doğrulaması: companion goal, pet-goal, Laya brain integration, vision-event ve Laya engine testleri **52 passed**; ardından brain + companion goal altkümesi **23 passed**. Autonomy YAML parse edildi, `git diff --check` temiz.
- Faz 2.6/3.8 regression doğrulaması ve geniş Laya ilişkili küme: BehaviorComposer mood-tone aktarımı, idle heartbeat sahipliği, GoalSelector TTL, spinal reflex, barge-in ve VLM olayları dahil **96 passed**; diff kontrolü temiz.
- Faz 3.1/3.7/4.1 güvenlik ve sahiplik sınırı doğrulandı: non-face owner/person/hazard vision event'leri Laya'ya sınıflandırma için ulaşır, ancak ikinci mood etkisi üretmez. Direct tool dispatch ve action safety bypass eklenmez.
- BehaviorComposer `say` planı artık isteğe bağlı `language` alanını `_speak_with_mood()`'a aktarır; alan yoksa önceki çağrı imzası/algılama davranışı korunur. Mood-tone regression testi dili açıkça belirleyerek deterministik hale getirildi.
- Tam doğrulama (2026-09-25): `pytest tests -x -q` **938 passed in 67.62s**. Komut hazır Python 3.12 runtime ile çalıştırıldı; runtime `Lib/site-packages` yolu `.venv/Lib/site-packages` yolundan önce ayarlanarak cp312 `pydantic_core` kullanıldı. Python derlemesi ve `git diff --check` temiz.
- Agent adapter regresyonu eklendi: Laya fast-path sınıflandırmasının world/visual context ile çağrıldığını ve kararın aynı tur için cache'lendiğini; normal sohbetin kısa olsa bile System 2'de kaldığını; sınıflandırma sırasında ToolRegistry dispatch yapılmadığını doğrular (`tests/modules/agent_core/test_laya_agent_fast_path.py`). Hedefli Agent/Laya kümesi **29 passed**.
- Son tam doğrulama (2026-09-25): `pytest tests -x -q` **940 passed in 41.68s**; testler hazır Python 3.12 runtime ve runtime `Lib/site-packages` önce gelecek şekilde çalıştırıldı. Kalan açık işler: güvenli ve yapılandırılmış Laya action argüman/actuator sözleşmesi oluşana kadar doğrudan Laya tool dispatch'i yok; arbiter/safety bypass yok; gerçek hedef cihazda canlı model/donanım kabul koşusu yapılmadı.
- Faz 5.3/5.4 tamamlandı olarak belgelendi: Brain VocalMixin, yüklü Laya modelinden emergency kararını alıp `BargeInController`'a geçiriyor; tek kelimelik acil ifade TTS'i kesiyor. LayaEngine config'indeki emergency threshold tek kaynak olarak kalıyor. Uçtan uca regression `test_laya_emergency_reaches_brain_barge_in_controller` eklendi.
- Güncel tam doğrulama (2026-09-25): `pytest tests -x -q` **941 passed in 41.48s**. Açık işler güvenli action argüman/actuator sözleşmesinin tasarımı ve gerçek hedef cihazda canlı model/donanım kabul koşusudur; arbiter ve safety bypass'ları uygulanmaması bilinçli karardır.
- Laya doğrudan action tasarım notu `.sentrybot/context/laya-action-contract.md` eklendi. Mevcut engine'in yalnızca hedef modül sınıflandırdığı ve `suggested_action` alanını doldurmadığı kayda geçirildi. Önerilen proposal şeması, fail-closed doğrulama/red koşulları, ToolRegistry/arbiter/runtime safety üzerinden dispatch gereksinimleri ve gerçek SpinalCord motor-stop rollout kapıları tanımlandı. Bu dokümanla dispatch açılmadı.
- Çıktı sözleşmesi araştırması: kurulu Laya 0.3.5 `Agent.system_one()` yalnız `choice`, `score`, `noul` başlıklarını işler; her biri typed answer, confidence/probabilities döndürür. JSON/action argument head yok; finite safe proposal gelecekte birden çok bounded choice cevabından türetilebilir. Cache model ile gerçek inference denemesi Python 3.12 + mevcut venv Torch `torch_python.dll` bağımlılığı nedeniyle WinError 126 ile yüklenemedi; model davranışı ek action soruları için hâlâ canlı doğrulanmadı. Dispatch kapalı kaldı.
- Uyumluluk çözümü denemesi: izole `.laya_runtime` hedefine CP312 Torch kurulumu onaylandı; 124.1 MB wheel indirmesi 7.6 MB'tan sonra yaklaşık 73 kB/s hız ve tekrarlı bağlantı kesintisi nedeniyle durduruldu. Paket kurulmadı, model inference yapılamadı. Bir sonraki çalışma ya çalışan CP311 runtime/Pi kullanmalı ya da CP312 wheel erişimini çözmeli.
- Donanım çağrısı yapmayan typed action proposal altyapısı eklendi: `laya_action_contract.py` yalnız confidence doğrulanmış, allowlist'teki `set_lights` için finite renk/efekt seçimlerini inert dict önerisine dönüştürür. Config `action_proposals.enabled: false` ile kapalı ve ToolRegistry dispatch bağlantısı yoktur. LayaEngine bu iki soru grubunu yalnızca feature açıldığında inference'a ekler. Testler invalid target/direct flag/allowlist/choice/confidence değerlerinde fail-closed davranışı ve default-off ayarını doğrular. Legacy `emergency_bypass_safety` default/config false yapıldı.
- Son tam doğrulama (2026-09-25): **958 passed in 47.79s**. Hedefli action contract + Laya engine kümesi 42 testte geçti; gerçek model inference'ı Torch indirme bağlantısı nedeniyle hâlâ beklemede.
- Mevcut Python 3.11 çalıştırıcısı altında cache model inference'ı tamamlandı. Bu, önceki notu günceller: Python 3.12 Torch wheel indirmesine artık gerek kalmadı. Gerçek Türkçe örneklerde eski emergency predicate'in `Işıkları kapat` (target emergency_stop 0.8273/direct 0.8297/urgency 2.059 confidence 0.541) ve normal sohbet (urgency 2.443 confidence 0.284) için false-positive üreteceği görüldü. `LayaDecision.is_emergency`, `is_emergency_decision`, `is_urgent` ve urgency mood effects confidence/direct gates ile düzeltildi. Açık emergency örnekleri target 0.934/direct 0.982 ve 0.950/0.970 ile kapıdan geçiyor.
- Deneysel action-color question setinde `Işıkları mavi yap` için renk `pink` confidence 0.2894 ve efekt `unspecified` confidence 0.3754 geldi. Fail-closed proposal doğru şekilde reddediyor; gerçek inference bu action alanlarının kalibre edilmediğini gösterdiği için `action_proposals.enabled` kapalı kalmalı.
- Emergency false-positive ve gerçek örnek regression kapsamı eklendi; hedefli Laya/emergency kümesi **55 passed**. Önceki 958 tam test sonucu confidence gate kodundan öncedir; yeni tam test koşusu bu değişikliklerle tekrar yapılmalıdır.
- Güncel tam doğrulama confidence gate değişiklikleriyle tekrarlandı: `pytest tests -x -q` **961 passed in 49.98s**. `git diff --check` ve değişen Laya Python dosyalarının `py_compile` kontrolü temiz.
- Offline gerçek-model kalibrasyon aracı `tools/evaluate_laya_action_proposals.py` eklendi. 14 Türkçe metin örneği için hedef/direct/color/effect seçimlerini, confidence kapılarından sonraki emergency kararını ve inert proposal üretimini raporlar; tool/hardware endpoint çağırmaz. Ölçüm: target top-choice 0.643, direct 0.929, açık renk 1/8 (0.125), açık effect 2/3, emergency 14/14, proposal 0. İlk rapordaki renk metriği unspecified negatiflerini sayıyordu; düzeltildi ve gerçek model tekrar çalıştırıldı. Bu sonuçlar renk proposal'ı için yetersiz; config kapalı tutulmalı.
- Düzeltilmiş summary-only ölçüm: target confidence>=0.60 coverage 0.571, kabul edilmiş target accuracy 0.625; direct confidence coverage 0.357, kabul edilmiş direct accuracy 1.0. Tekrar çalıştırılabilir komut: `python tools/evaluate_laya_action_proposals.py --summary-only` (Laya/Torch uyumlu Python 3.11 ortamı gerekir).
- Renk soru A/B deneyi: mevcut prompt 1/8 explicit renk doğruluğu, 5/6 no-color specificity ve 0 high-confidence false positive verdi. İki explicit/bilingual alternatif 8/8 explicit doğruluk ve 7/8 confidence coverage sağladı; ancak no-color specificity 1/6 ve 2/6'ya düştü, her birinde 2 high-confidence false color görüldü. Alt varyantlar uygulamaya alınmadı; mevcut conservative prompt ve kapalı feature korundu. Benchmark scripti şimdi current/TR-explicit/EN-explicit varyantlarını, confidence coverage/precision ve no-color high-confidence FP sayılarını raporluyor.
- Birleşik renk/kapat/no-light-action finite-choice deneyi: 14 örnekte genel doğruluk 0.500; explicit renk doğruluğu 0.750, confidence>=0.85 coverage 0.375, kabul edilen renk doğruluğu 1.000. No-color specificity 0.167 ve 3 high-confidence false positive. Birleşik soru da kabul edilmedi; proposal kapalı. Değerlendirme betiği yalnız offline inference yaptı ve hiç ToolRegistry/gateway/hardware çağırmadı.
- Evaluator 32 Türkçe calibration örneğine genişletildi (18 explicit color/off, 14 no-color kontrolü). Current color sorusu explicit doğruluk 0.111, no-color specificity 0.857 ve yüksek güvenli FP 0; Türkçe explicit varyant 1.000/0.778 coverage/0.214 specificity/4 FP; English-bilingual varyant 0.944/0.889 coverage/0.286 specificity/5 FP. Joint action varyantı overall 0.625, explicit color 0.778, coverage 0.222, specificity 0.429 ve 4 FP. Emergency 32/32, proposal 0. Sonuçlar feature'ın kapalı kalmasını destekliyor; bağımsız holdout ve deterministik parser baseline'ı henüz gerekli.
- Final holdout (30 örnek; 14 explicit color/off, 16 control; calibration/dev metinleriyle çakışma yok) üzerinde evaluator-only deterministik parser 0.967 overall doğruluk, 0.929 explicit doğruluk ve 1.000 unspecified özgüllük verdi. Laya current/TR/EN/joint overall doğruluk 0.433/0.533/0.567/0.500; explicit doğruluk 0.143/1.000/1.000/0.786; specificity 0.688/0.125/0.188/0.250. Açık TR/EN soruları sırasıyla 8 ve 9 yüksek güvenli false positive üretti. Parser production'a taşınmadı; küçük, elle yazılmış sette sınırlı kanıt olduğu ve action proposal kapalı kaldığı not edildi. Final holdout üzerinden tekrar kalibrasyon yapılmamalı.
- Sınıf başına beş örnek içeren yeni 30 örnekli intent/safety holdout'unda target accuracy 0.600 oldu (neopixel 0.400, arduino 1.000, emergency_stop 0.800, speak 0.200, camera 1.000, system2_chat 0.200). Target güven kapısı coverage 0.700/accepted accuracy 0.714; direct accuracy 0.900, coverage 0.700/accepted accuracy 1.000. Confidence-gated emergency 0.933, FP 0/FN 2; high-urgency 0.833, FP 0/FN 5. Effect 2/4 doğruluk ve 0/4 confidence kabulü verdi. Bu holdout değiştirilmeden kaldı; direct action/dispatch açılmadı.
- 32 örnekli dev split'te ek target/effect soruları ölçüldü. Uzun TR target varyantı 0.188 doğruluk, 0.174 accepted doğruluk ve 0.719 coverage; kısa EN target varyantı 0.500, 0.667 ve 0.188 verdi. Explicit effect varyantı beş örnekte 0.800 top-choice, 0.400 coverage, 0.500 accepted accuracy sağladı. Hiçbir aday seçilmedi; production config/prompt değişmedi, intent holdout kullanılmadı.
- 2026-09-26 dengeli 30 örneklik intent dev splitinde current/TR-explicit/EN-explicit target doğruluğu 0.467/0.500/0.600; accepted doğruluk 0.667/0.857/0.786 ve coverage 0.500/0.467/0.467 oldu. Effect alternatifleri 4 örnekte 0.500 doğrulukta kaldı. TR target adayı bir defa holdout'ta sınandı: target accuracy 0.600→0.433, accepted accuracy 0.714→0.647 ve emergency accuracy 0.933→0.900 (FN 2→3); reddedildi. Üretim davranışı ve proposal config'i değişmedi. Bu holdout gelecek prompt kalibrasyonu için artık kullanılmamalı; yeni candidate yeni untouched set gerektirir.
- İkili explicit-audio intent sorusu aynı dev splitinde 0.733 doğruluk aldı, ancak precision/recall 0.0 oldu (3 FP, 5/5 speak FN). Confidence .60/.80/.90 refiner hedef doğruluğunu artırmadı; aday reddedildi.
| `modules/autonomy/services/spinal_cord_reflex.py` | 2 |
| `modules/autonomy/services/behavior_composer.py` | 2 |
| `modules/autonomy/services/companion_goal_selector.py` | 2 |
| `modules/agent_core/services/world_state.py` | 3 |
| `modules/agent_core/services/sensor_loop.py` | 3 |
| `modules/agent_core/services/action_arbiter.py` | 3 |
| `modules/agent_core/services/idle_behavior.py` | 3 |
| `modules/vlm_bridge/services/processor.py` | 4 |
| `modules/vlm_bridge/services/vision_event_bus.py` | 4 |
| `modules/vlm_bridge/services/visual_context.py` | 4 |
| `modules/vlm_bridge/services/face_emotion.py` | 4 |
| `modules/voice/speak/xSpeakService.py` | 5 |
| `modules/voice/audio_router.py` | 5 |
| `modules/autonomy/services/barge_in.py` | 5 |
| `modules/agent_core/services/progress.py` | 6 |
| `modules/agent_core/services/safety_filter.py` | 6 |
- 2026-09-27: Offline explicit-audio literal parser evaluation completed. Intent dev: 30/30; separate 30-example audio holdout: 0.867 accuracy, 0.667 precision, 1.000 recall (4 false positives). Holdout findings reject parser for production gating. Added repeatable `--audio-parser-holdout-only` mode that lazily avoids Laya/Torch import; no dispatch/hardware path. No production behavior/config changed.
- 2026-09-27: Added pure request-ID binding and fail-closed exact-schema validation for inert `set_lights` proposals. It enforces request match, policy enablement/allowlist, exact fields/enums, and confidence floor. It is deliberately not connected to dispatch and does not enable production proposals. Targeted contract tests: 25 passed.
- 2026-09-27: Confirmed API `trace_id` can be caller-provided and should not authorize proposal binding. Agent `step()` now creates a distinct internal UUID for each admitted turn, binds any inert Laya proposal to it, and clears the active ID in `finally`. Added adapter regression coverage; no dispatcher/tool execution was connected.
- 2026-09-27: Reviewed the existing lights execution path before dispatcher work. `set_lights` enters agent-core ActionArbiter and its ActionSafetyFilter, then handler lease + Autonomy client; current filter has no lights-specific capability approval and the handler does not call Autonomy CapabilityExecutor. ToolRegistry arbiter is a separate resource gate. Dispatcher/simulation seam deferred until the runtime owner gate exists; proposal remains disabled.

## 2026-09-27 — kapanış özeti

### Bu fazda tamamlananlar

- LayaEngine ve Agent/System 1 fast-path entegrasyonu; kısa sohbeti System 2'ye bırakma ve karar aşamasında araç çalıştırmama sınırı.
- Affective/vision sinyalleri, confidence-gated emergency kararları ve regression kapsamı.
- Fail-closed, yalnızca `set_lights` için typed inert proposal builder; exact schema/confidence/allowlist validator.
- Her Agent step için internal UUID ve Laya proposal request binding. Caller-provided `trace_id` yalnız telemetri kimliği.
- Offline kalibrasyon/evaluator, ayrık ama küçük ve elle etiketlenmiş color/intent/audio kümeleri; güvenli olmayan prompt/parser adayları reddedildi.
- 2026-09-27 son tam doğrulama: **970 passed**; action dispatch ve hardware çağrısı açılmadı.

### Bilinçli olarak tamamlanmayan rollout işleri

- Haricen gözden geçirilmiş, daha geniş intent/safety korpusu yok; var olan holdout'lar tükenmiş durumda.
- Mevcut ışık eylem yolu `ActionArbiter` ve `ActionSafetyFilter` kullanıyor, fakat Autonomy `CapabilityExecutor` lights onayı vermiyor/uygulamıyor. Laya-specific owner approval kapısı yok.
- Gerçek Laya modelinin uyumlu runtime ve Raspberry Pi üzerinde final kabulü yapılmadı.
- Dispatcher, emergency-stop Arduino contract/ACK, zero-side-effect ret matrisi ve donanım kabulü yapılmadı.

Bu nedenle entegrasyon kod fazı tamamlandı; fiziksel eylem rollout'u **release-blocked** durumunda. `action_proposals.enabled` kapalı kalmalı. Ayrıntılı sıra ve açma koşulları `.sentrybot/laya_integration_todo.md` başındadır.

