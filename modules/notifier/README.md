# Notifier

Telegram/Discord bildirimleri için basit köprü.

## API
- GET `/notify/healthz`
- POST `/notify/telegram` `{ text }` (configte token/chat_id gerektirir)
- POST `/notify/discord` `{ text }` (configte webhook gerektirir)
- POST `/notify/test`
