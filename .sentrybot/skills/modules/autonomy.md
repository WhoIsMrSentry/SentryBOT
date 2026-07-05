# Skill: autonomy

## Ana bileşen
- Sınıf: `xAutonomyService` in `modules/autonomy/xAutonomyService.py`
- Mission: Sense-Think-Act beyin döngüsü, duygu motoru, LLM kararları

## API özeti
- `GET /state` → `get_state()` → —
- `POST /interaction` → `report_interaction()` → —
- `POST /apply_actions` → `apply_actions()` → —
- `GET /lights/palettes` → `list_palettes()` → —
- `POST /lights/palettes/{name}` → `set_palette()` → —
- `DELETE /lights/palettes/{name}` → `delete_palette()` → —
- `POST /start` → `start_brain()` → —
- `POST /stop` → `stop_brain()` → —

## Dış ilişkiler (neden)
- → [[agent_core]] (http): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- → [[agent_core]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- → [[agent_core]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- → [[animate]] (http): Duygu durumuna göre vücut animasyonu (stretch, sit, look_around) tetikler.
- → [[arduino_serial]] (arduino): Karar sonrası servo/hareket komutlarını donanıma iletir.
- → [[arduino_serial]] (import): Karar sonrası servo/hareket komutlarını donanıma iletir.
- → [[arduino_serial]] (registry): Karar sonrası servo/hareket komutlarını donanıma iletir.
- → [[common]] (import): `autonomy` → `common`: Kanonik duygu taksonomisi (tone/LED/yüz) için ortak sözlük.
- → [[config_center]] (import): `autonomy` içinde `log_redact` import edilir; `config_center` modülünün yeteneğini kullanır (Merkezi config okuma/yazma, hot-reload).
- → [[gateway]] (import): `autonomy` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).

## Gelen ilişkiler (neden)
- ← [[agent_core]] (import): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- ← [[agent_core]] (registry): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- ← [[gateway]] (import): `gateway` kod içinde `autonomy` modülünü import eder (`xAutonomyService`) — Sense-Think-Act beyin döngüsü, duygu motoru, LLM kararları.
- ← [[gateway]] (import): `gateway` kod içinde `autonomy` modülünü import eder (`api`) — Sense-Think-Act beyin döngüsü, duygu motoru, LLM kararları.
- ← [[hardware]] (import): Sistem yükü verisini otonomi beyinine bildirir.

## Tam bilgi
`.sentrybot/obsidian/modules/autonomy.md` (64 dosya, 7250 satır)
