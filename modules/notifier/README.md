# Notifier

A lightweight bridge for Telegram, Discord, and WhatsApp Web alerts. Telegram support optionally spins up a long-polling bot so you can issue commands back into the platform.

## Setup
1. Fill out `modules/notifier/config/config.yml`:
```
telegram:
	bot_token: "123:ABC"
	chat_id: "-100..."        # default outbound target
	allowed_user_ids: [123456] # empty list means everyone
	polling:
		enabled: true            # toggle Telegram bot
		interval_sec: 2.5
whatsapp_web:
	enabled: false
	recipient: "+905551111111"
	send_mode: "instant"      # instant | schedule
	schedule_delay_sec: 90     # only used when send_mode=schedule
	wait_time_sec: 15          # pywhatkit wait before typing
	close_time_sec: 5          # wait before tab close
	tab_close: true            # close tab after send
discord:
	webhook: ""
quiet_hours:
	enabled: false
	start: "23:00"
	end: "08:00"
```

2. Run the service via `python -m modules.notifier.xNotifierService` (or through your orchestrator).

## API
- GET `/notify/healthz`
- POST `/notify/telegram` `{ text, chat_id? }` (requires token + chat_id in config)
- POST `/notify/discord` `{ text }` (requires webhook in config)
- POST `/notify/whatsapp` `{ text, to?, delay_sec? }` (drives the WhatsApp Web sender)
- POST `/notify/test`

## Telegram bot
- When `polling.enabled` is true, the bot listens for `/start`, `/ping`, `/help` in the background.
- Quiet hours suppress outgoing alerts and respond with an informational notice instead.
- If `allowed_user_ids` is non-empty, only those Telegram user IDs can interact.
- Extended commands (proxied to the gateway `base_url`):
	- `/status` overall module health
	- `/snap` camera snapshot
	- `/stream` MJPEG stream info
	- `/pt <pan> <tilt>` pan/tilt degrees
	- `/pan <deg>` and `/tilt <deg>` single-axis helpers
	- `/neofill r g b`, `/neoclear` NeoPixel controls
	- `/say <text>` triggers the speak service

## WhatsApp Web sender
- Install `pywhatkit` (and its dependencies) inside the environment: `pip install pywhatkit`.
- Log into WhatsApp Web manually and keep the browser session open; the sender hijacks that session to send a message.
- Configure the `whatsapp_web` block:
	- `recipient` must be an international MSISDN (e.g., `+9055...`).
	- `send_mode: instant` uses `pywhatkit.sendwhatmsg_instantly` (~15 s prep window).
	- `send_mode: schedule` falls back to `pywhatkit.sendwhatmsg`, so delivery happens at least `schedule_delay_sec` seconds later.
	- `wait_time_sec`, `close_time_sec`, and `tab_close` mirror pywhatkit’s browser automation knobs.
- POST `/notify/whatsapp` with `{ "text": "Hello" }` to deliver; optionally override the destination with `to`.
- This flow is outbound-only: no inbound commands or media uploads through WhatsApp Web.
- During sending, avoid touching keyboard/mouse—pywhatkit simulates human interaction and can be interrupted easily.
