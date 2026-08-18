# Autonomy

SentryBOT'un sürekli çalışan davranış beynidir. `AutonomyBrain`, duyulardan ve diğer modüllerden gelen sinyalleri birleştirir; ihtiyaç, duygu, hedef ve güvenli eylem kararları üretir; ardından konuşma, ifade, hareket ve hafıza katmanlarını koordine eder.

## Ana Yetenekler

- Sense-think-act beyin döngüsü
- Duygu, ihtiyaç ve companion hedef seçimi
- Dünya hafızası, RAG, ihtiyaç yanlı bellek ve karar gölgesi
- Ses, görüntü ve olay girdilerinden proaktif tepki üretimi
- Sahip tanıma, geçici yetki ve owner-guard davranışları
- Güvenli navigasyon, topomap ve dinlenme noktası akışları
- LED palet yönetimi ve ifade orkestrasyonu
- Dry-run destekli otomatik hedef yürütme

## Mimari

- Giriş noktası: `xAutonomyService.py`
- Router: `api/router.py`
- Ana beyin: `services/brain.py`
- İstemci katmanı: `services/client.py`
- Alt sistemler: `world_memory*`, `needs_engine.py`, `companion_goal_*`, `owner_person_learning.py`, `safe_navigation.py`, `topomap_motion_executor.py`, `vision_context_*`, `audio_event_needs_bridge.py`

Modül, klasik "canlı mod" davranışlarının ötesine geçmiş durumda; artık semantik hafıza, living companion ihtiyaç modeli ve güvenli otomatik eylem geçidi içeriyor.

## Bağımlılıklar

- `agent_core`: üst seviye ajan çağrıları ve olay tabanlı reaksiyonlar
- `speech`: final konuşma metni ve ses kesme entegrasyonu
- `speak`: yanıtların seslendirilmesi
- `interactions`: olay, efekt ve temel LED durumları
- `state_manager`: dominant duygu ve operasyonel durum paylaşımı
- `animate`, `arduino_serial`: jest, servo ve hareket yürütme
- `social_db`: kişi/ilişki hafızası
- `gateway`: servis URL çözümleme

## API

Gateway altında `/autonomy/*` olarak sunulur.

### Temel Durum

- `GET /autonomy/state`
- `POST /autonomy/interaction`
- `POST /autonomy/speech`
- `POST /autonomy/apply_actions`
- `POST /autonomy/start`
- `POST /autonomy/stop`

### Needs, Goal, Living Companion

- `GET /autonomy/needs`
- `GET /autonomy/goal`
- `GET /autonomy/living/status`
- `GET /autonomy/living/needs`
- `POST /autonomy/living/tick`
- `POST /autonomy/living/vision`
- `POST /autonomy/living/audio`
- `POST /autonomy/living/boredom`
- `POST /autonomy/living/sound-interrupt`
- `GET /autonomy/living-needs`
- `POST /autonomy/living-needs/tick`
- `GET /autonomy/goal/auto`
- `POST /autonomy/goal/auto/tick`
- `GET /autonomy/goal/execution`
- `POST /autonomy/goal/execute`
- `POST /autonomy/goal/simulate`

### World Memory and RAG

- `GET /autonomy/memory`
- `GET /autonomy/memory/schema`
- `GET /autonomy/memory/recent`
- `GET /autonomy/memory/history`
- `GET /autonomy/memory/search`
- `GET /autonomy/memory/context`
- `POST /autonomy/memory/observe`
- `POST /autonomy/memory/clear`
- `GET /autonomy/memory/autowrite`
- `POST /autonomy/memory/autowrite`
- `GET /autonomy/memory/rag`
- `GET /autonomy/memory/rag/recent`
- `POST /autonomy/memory/rag/observe`
- `GET /autonomy/memory/rag/recall`
- `GET /autonomy/memory/rag/context`
- `POST /autonomy/memory/rag/forget`
- `GET /autonomy/memory/needs-bias`
- `POST /autonomy/memory/needs-bias/evaluate`
- `GET /autonomy/memory/decision-shadow`
- `POST /autonomy/memory/decision-shadow/evaluate`

### Navigation, Owner, Runtime

- `GET /autonomy/navigation/status`
- `GET /autonomy/navigation/places`
- `POST /autonomy/navigation/places/learn`
- `GET /autonomy/navigation/safe-places`
- `POST /autonomy/navigation/safe-places`
- `POST /autonomy/navigation/rest-corner`
- `GET /autonomy/navigation/topomap`
- `POST /autonomy/navigation/topomap/learn`
- `POST /autonomy/navigation/goal`
- `GET /autonomy/assets/status`
- `GET /autonomy/pi-runtime/status`
- `GET /autonomy/owner/status`
- `POST /autonomy/owner/learn`
- `POST /autonomy/owner/identify`

### Lighting

- `GET /autonomy/lights/palettes`
- `POST /autonomy/lights/palettes/{name}`
- `DELETE /autonomy/lights/palettes/{name}`

## Konfigürasyon

Bu modül modül-içi `config/config.yml` kullanır. Önemli alanlar:

- `endpoints.*`: `speech`, `interactions`, `state_manager`, `animate`, `agent_core`, `arduino`, `speak`
- `vision_hooks.*`
- `owner.*`
- `speech_quiet_hours.*`
- `behaviors.idle_tree.*`
- `defaults.body_language.*`
- `scenes.*`
- `offline_mode.*`

## Otonomluk Açısından Önemi

Bu modül, projedeki otonomluğun merkezidir. Pasif API cevaplayıcısı değildir; kendi döngüsünü çalıştırır, yeni bağlamlardan hafıza yazar, ihtiyaç ve hedef üretir, bazı akışları dry-run güvenlik kapılarıyla otomatik değerlendirebilir ve diğer modülleri davranış planının bir parçası olarak tetikler.
