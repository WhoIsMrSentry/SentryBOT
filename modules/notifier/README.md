# Notifier

Telegram/Discord bildirimleri için basit köprü. İsteğe bağlı Telegram botu uzun anket (polling) ile çalışır.

## Kurulum
1) `modules/notifier/config/config.yml` içinde bot ayarlarını doldur:
```
telegram:
	bot_token: "123:ABC"
	chat_id: "-100..."        # varsayılan gönderim hedefi
	allowed_user_ids: [123456] # boş ise herkes
	polling:
		enabled: true            # botu aktif eder
		interval_sec: 2.5
discord:
	webhook: ""
quiet_hours:
	enabled: false
	start: "23:00"
	end: "08:00"
```

2) Servisi çalıştır: `python -m modules.notifier.xNotifierService` veya üst seviye orchestrator.

## API
- GET `/notify/healthz`
- POST `/notify/telegram` `{ text, chat_id? }` (configte token/chat_id gerektirir)
- POST `/notify/discord` `{ text }` (configte webhook gerektirir)
- POST `/notify/test`

## Telegram bot
- `polling.enabled` true ise bot arkaplanda `/start`, `/ping`, `/help` komutlarını dinler.
- Mesaj geldiğinde quiet hours etkinse bildirim göndermez, bilgi mesajı yollar.
- `allowed_user_ids` doluysa sadece listedekileri kabul eder.
- Genişletilmiş komutlar (gateway base_url üzerinden):
	- `/status` modül sağlık özeti
	- `/snap` kamera snapshot linki
	- `/stream` kamera stream linki
	- `/pt <pan> <tilt>` pan/tilt kontrolü (derece)
	- `/pan <deg>`, `/tilt <deg>` tek eksen
	- `/neofill r g b`, `/neoclear` NeoPixel kontrolü
	- `/say <metin>` TTS (speak servisi)
