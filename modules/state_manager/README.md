# State Manager

Global durum ve duygular için hafif bir depolama ve API.

## API
- GET `/state/healthz`
- GET `/state/get`
- POST `/state/set/operational` `{ value: string }`
- POST `/state/set/emotions` `{ values: string[] }`
