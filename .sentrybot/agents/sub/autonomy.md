# Sub-Agent: autonomy-specialist

## Uzmanlık
`xAutonomyService` ve `autonomy` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/autonomy.md`

## Bileşen haritası
- `AffectiveAppraisal` — Turns events into mood deltas and applies them to a mood manager.
- `BargeInController` — modules/autonomy/services/barge_in.py
- `AutonomyBrain` — modules/autonomy/services/brain.py
- `AnimationSupportMixin` — Provides reusable micro-movements and animation fallbacks.
- `OwnerGuardMixin` — Encapsulates owner scanning, permissions, and request throttling.
- `ResponseTagMixin` — Sentry persona etiketlerini çözümleyip donanıma yönlendirir.
- `SceneMixin` — Runs small action timelines combining light/motion/speech.
- `TimelineMixin` — Keeps a lightweight daily journal of interactions.
- `VisionMixin` — Handles periodic vision polling and reactions.
- `VocalMixin` — Adds speaking helpers that respect robot mood.
- `ServiceClient` — modules/autonomy/services/client.py
- `CompanionRituals` — Low-frequency social rituals to improve companion continuity.

## Dış bağlantılar (neden)
- [[agent_core]] (http): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- [[agent_core]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- [[agent_core]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- [[animate]] (http): Duygu durumuna göre vücut animasyonu (stretch, sit, look_around) tetikler.
- [[arduino_serial]] (arduino): Karar sonrası servo/hareket komutlarını donanıma iletir.
- [[arduino_serial]] (import): Karar sonrası servo/hareket komutlarını donanıma iletir.
- [[arduino_serial]] (registry): Karar sonrası servo/hareket komutlarını donanıma iletir.
- [[common]] (import): `autonomy` → `common`: Kanonik duygu taksonomisi (tone/LED/yüz) için ortak sözlük.
- [[config_center]] (import): `autonomy` içinde `log_redact` import edilir; `config_center` modülünün yeteneğini kullanır (Merkezi config okuma/yazma, hot-reload).
- [[gateway]] (import): `autonomy` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- [[ollama]] (registry): Duygu motoru ve karar üretimi için yerel LLM'e sorar.
- [[social_db]] (import): Kişi hafızası ve ilişki seviyelerini okur/günceller.

## Gelen bağlantılar (neden)
- [[agent_core]] (import): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- [[agent_core]] (registry): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- [[gateway]] (import): `gateway` kod içinde `autonomy` modülünü import eder (`xAutonomyService`) — Sense-Think-Act beyin döngüsü, duygu motoru, LLM kararları.
- [[gateway]] (import): `gateway` kod içinde `autonomy` modülünü import eder (`api`) — Sense-Think-Act beyin döngüsü, duygu motoru, LLM kararları.
- [[hardware]] (import): Sistem yükü verisini otonomi beyinine bildirir.
