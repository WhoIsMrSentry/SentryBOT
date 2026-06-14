# SentryBOT — Companion & Vision Roadmap

> **Tek kaynak:** Bu dosyayı okuyarak sıradaki işe devam et.  
> Son güncelleme: 2026-06-14

## Durum özeti

| Alan | Durum | Not |
|------|-------|-----|
| Pip OLED + idle ambient | ✅ Tamamlandı | main'e merge |
| NeoPixel renk geçişi | ✅ Tamamlandı | `emote` + `set_neopixel` |
| Sesli duygu emirleri | ✅ Tamamlandı | `brain.express()` |
| LLM duygu araçları | ✅ Tamamlandı | tri-layer + tool enum |
| Agent remote vision fallback | ✅ Tamamlandı | `vision_input_available()` |
| LED çift tetikleme | ✅ Düzeltildi | interactions emotion LED kuralları kaldırıldı |
| Pasif mood sahneleri | ✅ Tamamlandı | 15 canonical scene |
| Kamera / yerel VLM | 🚫 Beklemede | `camera.enabled: false` |
| Uzak VLM ingest | ✅ Hazır | `POST /vlm/results` |
| Kişi empati + konuşma | ✅ Tamamlandı | `speak_on_mirror: true` |

---

## A — İfade & Duygu `DONE`

- [x] NeoPixel RGB + `/neopixel/emote` palette yolu (`expression_director`)
- [x] Türkçe duygu emirleri → `express()`
- [x] `set_emotion` tool → OLED+LED+`emotion:{canon}`
- [x] tri-layer: `autonomy` + `agent_core` default (modül + agent.yaml)
- [x] Koşullu `autonomy.excited` (`speech_reactions`)
- [x] Pasif mood: `anger_threshold: 38`, tüm `emotion_*` sahneleri
- [x] OLED `emotion:joy` alias

**Harita:** `modules/common/config/emotions.yml`

---

## B — VLM Bridge `REMOTE_ONLY`

### Çalışan
- `POST /vlm/results` remote ingest
- Agent araçları: kamera **veya** VLM cache (`modules/common/vision_availability.py`)
- `remote_multimodal` şablonu (`enabled: false`)

### Kamera gelince
- [ ] `camera.enabled: true` + `include.camera: true`
- [ ] `hybrid_local_capture` / `processing_mode: local`
- [ ] `remote_multimodal.enabled: true` + PC endpoint
- [ ] Pi-side capture pusher (kamera ile)

---

## C — IMX500 `BLOCKED` (kamera yok)

---

## D — Companion empati `DONE`

- [x] Remote ingest → `express()` mirror
- [x] `speak_on_mirror: true`
- [x] Piservo kulakları: `emotion:*` event (interactions bridge)

---

## E — Kalan düşük öncelik

| Sorun | Öncelik |
|-------|---------|
| `architecture_vlm_bridge.md` güncel değil | P3 |
| Git LFS hook makinede yok | ops |
| config_center `camera.enabled` hot-reload | P3 |

---

## Kamera kapalı (aktif)

```yaml
include.camera: false
camera.enabled: false
vision.processing_mode: remote
vision.hybrid_local_capture: false
vision.follow.enabled: false
```

---

## Test

```bash
python -m pytest modules/common/tests/test_vision_availability.py \
  modules/autonomy/tests/ modules/agent_core/tests/test_tool_progress.py \
  modules/interactions/tests/test_smoke.py -q --maxfail=1
```

## Manuel (kamera olmadan)

- `POST /vlm/results` → agent `get_vision` çalışmalı (cache doluysa)
- "sinirlen" → angry + kırmızı (tek LED animasyonu, çift değil)
- Uzak ingest joy + empati → konuşma mirror ("Mutlu görünüyorsun…")
