# Autonomy

SentryBOT'un sürekli çalışan davranış beynidir. `AutonomyBrain`, duyulardan ve diğer modüllerden gelen sinyalleri birleştirir; ihtiyaç, duygu, hedef ve güvenli eylem kararları üretir; ardından konuşma, ifade, hareket ve hafıza katmanlarını koordine eder.

## Ana Yetenekler

- Sense-think-act beyin döngüsü (event-driven, ~100ms cycle)
- Duygu (MoodManager), ihtiyaç (NeedsEngine) ve Companion hedef seçimi
- Dünya hafızası (WorldMemory), RAG, ihtiyaç yanlı bellek ve karar gölgesi
- Ses, görüntü ve olay girdilerinden proaktif tepki üretimi
- Sahip tanıma, geçici yetki ve owner-guard davranışları
- Güvenli navigasyon, topomap ve dinlenme noktası akışları
- LED palet yönetimi ve ifade orkestrasyonu (ExpressionArbiter üzerinden)
- Dry-run destekli otomatik hedef yürütme

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xAutonomyService.py`
- Router: `api/router.py` (+ `api/companion_routes.py`, `api/memory_routes.py`)
- **Ana Beyin (Parçalanmış)**: `services/brain.py` (facade) → `services/brain_parts/`:
  - `decision.py` - Eylem kararı, tool calling koordinasyonu
  - `emotion_sync.py` - MoodManager, duygu durumu senkronizasyonu
  - `scenario_rituals.py` - Companion ritüeller, sahne yönetimi
  - `speech_react.py` - Ses tepkileri, prosody
  - `vocal_prosody.py` - Ses tonu, hız, vurgu profilleri
- **Client Katmanı**: `services/client.py` → `services/client_parts/` (modüler)
- **Hedef Yürütme**: `services/companion_goal_executor.py`, `companion_goal_selector.py`, `companion_goal_policies.py`, `companion_goal_plans.py`, `companion_goal_translator.py`
- **Diğer**: `behavior_planner.py`, `interaction_feedback.py`, `mood.py`, `topomap_motion_executor.py`, `hardware_policy.py`, `brain_init.py`

## Bağımlılıklar (Güncel Modül Adları)

- `agent_core`: Üst seviye ajan çağrıları ve olay tabanlı reaksiyonlar (brain.agent provider)
- `voice/speech`: Final konuşma metni ve ses kesme entegrasyonu
- `voice/speak`: Yanıtların seslendirilmesi
- `expression/interactions`: Olay, efekt ve temel LED durumları
- `system_control/state_manager`: Dominant duygu ve operasyonel durum paylaşımı
- `expression/animate`: Jest, servo ve hareket yürütme
- `arduino_serial`: Donanım hareket komutları (track, pose, estop)
- `cognitive_memory` (eski `social_db`): Kişi/ilişki hafızası (repository pattern)
- `gateway`: Servis URL çözümleme
- `vlm_bridge`: Görsel bağlam (vision context bridge)
- `expression`: ExpressionArbiter (LED/servo/OLED lease arbitrajı)

## API

Gateway altında `/autonomy/*` olarak sunulur.

### Temel Durum

- `GET /autonomy/state`
- `POST /autonomy/interaction`
- `POST /autonomy/speech`
- `POST /autonomy/apply_actions`
- `POST /autonomy/start`
- `POST /autonomy/stop`

### Companion Routes (`api/companion_routes.py`)

Not: `companion_routes.py` route'ları `/companion/` prefix'siz ana `/autonomy` router'ına eklenir.

- `GET /autonomy/needs`
- `GET /autonomy/goal`
- `POST /autonomy/goal/auto/tick`
- `POST /autonomy/sound-interrupt`

### Memory Routes (YENİ: `api/memory_routes.py`)

- `GET /autonomy/memory/context`
- `POST /autonomy/memory/observe`
- `GET /autonomy/memory/search`
- `GET /autonomy/memory/recent`
- `POST /autonomy/memory/autowrite`
- `GET /autonomy/memory/rag`

### Navigation, Owner, Runtime

- `GET /autonomy/navigation/status`
- `GET /autonomy/navigation/places`
- `POST /autonomy/navigation/places/learn`
- `GET /autonomy/navigation/topomap`
- `POST /autonomy/navigation/topomap/learn`
- `GET /autonomy/owner/status`
- `POST /autonomy/owner/learn`
- `POST /autonomy/owner/identify`
- `GET /autonomy/runtime/profile`, `POST /autonomy/runtime/profile/switch` — **planlanan** (API yüzü henüz yok)

### Lighting (ExpressionArbiter üzerinden)

- `GET /autonomy/lights/palettes`
- `POST /autonomy/lights/palettes/{name}`
- `DELETE /autonomy/lights/palettes/{name}`

### Diğer Uçlar

- `/autonomy/mood`
- `/autonomy/express/{emotion}`
- `/autonomy/audio-event` (+ `/observe`)
- `/autonomy/vision-context` (+ `/observe`)
- `/autonomy/navigation/rest-corner`
- `/autonomy/navigation/goal`
- `/autonomy/assets/status`
- `/autonomy/pi-runtime/status`
- `/autonomy/memory/needs-bias` (+ `/evaluate`)
- `/autonomy/memory/decision-shadow` (+ `/evaluate`)
- `/autonomy/memory/schema` | `history` | `clear`
- `/autonomy/goal/execute` | `simulate` | `execution`
- `/autonomy/living-needs` (+ `/tick`)
- `/autonomy/scenario/replay` | `e2e`

## Konfigürasyon

Bu modül modül-içi `config/config.yml` + merkezi `config/agent.yaml` (autonomy section) kullanır.

Önemli alanlar:
- `endpoints.*`: `speech`, `interactions`, `state_manager`, `animate`, `agent_core`, `arduino`, `speak` (gateway URL'leri)
- `vision_hooks.*`
- `owner.*`
- `speech_quiet_hours.*`
- `behaviors.idle_tree.*`
- `defaults.body_language.*`
- `scenes.*`
- `offline_mode.*`
- `realtime_profile.*` (hız/kalite profilleri)

## Otonomluk Açısından Önemi

Bu modül, projedeki otonomluğun merkezidir. Pasif API cevaplayıcısı değildir; kendi döngüsünü çalıştırır (`Brain.run_cycle`), yeni bağlamlardan hafıza yazar (`WorldMemory`), ihtiyaç ve hedef üretir (`NeedsEngine`, `CompanionGoalSelector`), bazı akışları dry-run güvenlik kapılarıyla otomatik değerlendirebilir ve diğer modülleri davranış planının bir parçası olarak tetikler.

**Davranış Otoritesi:** `autonomy` planlar → `agent_core` bir LLM turunu yürütür → `expression` yüz/ışık/kulak render eder. Ayrıntı: `.sentrybot/context/behavior-authority.md`.

Raspberry Pi'de `companion_goal_executor.follow_runtime_profile` gerçek donanımı `config/robot_execution_profiles.json` üzerinden açar; PC'de dry-run kalır.

## Bilinen Çakışma Riskleri (Bkz: `../otonomi_ve_cakisma_analizi.md`)

1. **Head Control** - `vlm_bridge`, `expression/animate`, `voice/speech` doğrudan `arduino.track()` çağırıyor, `HeadControlArbiter` bypass ediliyor
2. **NeoPixel** - `autonomy.mood` → `interactions` → `neopixel` yolu `ExpressionArbiter` lease'ını tanımıyor
3. **Memory Yazma** - `autonomy`, `agent_core/tools`, `vlm_bridge` eşzamanlı `cognitive_memory` DB'sine yazıyor (SQLite WAL + busy_timeout var ama transaction isolation yok)
4. **Event Fan-out** - Tek event (örn. `wakeword.detected`) 5-6 modülü tetikliyor, sıralama garantisi yok