# Skill: common

## Ana bileşen
- Sınıf: `EmotionRender` in `modules/common/emotion_vocab.py`
- Mission: Kanonik duygu sözlüğü (eyes/LEDs/ears/tone tek taksonomi)

## API özeti
- —

## Dış ilişkiler (neden)
- → [[camera]] (http): `common` HTTP ile `camera` modülüne erişir: Kamera stream veya snapshot ister.
- → [[gateway]] (import): `common` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- → [[vlm_bridge]] (http): `common` gateway veya doğrudan HTTP ile `vlm_bridge` API'sini çağırır (calls path `/vlm/context/latest`).
- → [[vlm_bridge]] (http): `common` gateway veya doğrudan HTTP ile `vlm_bridge` API'sini çağırır (calls path `/vlm/results/latest`).

## Gelen ilişkiler (neden)
- ← [[agent_core]] (import): `agent_core` kod içinde `common` modülünü import eder (`vision_availability`) — Kanonik duygu sözlüğü (eyes/LEDs/ears/tone tek taksonomi).
- ← [[agent_core]] (import): `agent_core` `common` modülünden `emotion_vocab` kullanır: Kanonik duygu taksonomisi (tone/LED/yüz) için ortak sözlük.
- ← [[autonomy]] (import): `autonomy` `common` modülünden `emotion_vocab` kullanır: Kanonik duygu taksonomisi (tone/LED/yüz) için ortak sözlük.
- ← [[neopixel]] (import): 23 duygu paleti emotion_vocab ile hizalanır.
- ← [[oled_faces]] (import): Yüz ifadesi ve duygu taksonomisini ortak sözlükten alır.
- ← [[piservo]] (import): Kulak pozisyonları duygu sözlüğü ile eşlenir.
- ← [[speak]] (import): Duygu tonu ve emotion_vocab ile TTS tonunu eşler.

## Tam bilgi
`.sentrybot/obsidian/modules/common.md` (8 dosya, 458 satır)
