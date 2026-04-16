# State Manager

Global durum ve duygular için hafif bir depolama ve API.

Bu modül robotun ortak state katmanıdır. Modlar, duygular, operasyonel bayraklar ve özel anahtarlar burada tutulur; böylece servisler aynı veriyi paylaşır ve restart sonrası state kaybolmaz.

## Ne İşe Yarar?
- State'i sqlite veya json backend ile kalıcı hale getirir.
- Temel alanları ve özel anahtarları tek bir API üzerinden günceller.
- Diğer modüllere ortak durum kaynağı sağlar.

## API
- GET `/state/healthz`
- GET `/state/get`
- POST `/state/set/operational` `{ value: string }`
- POST `/state/set/emotions` `{ values: string[] }`
- POST `/state/set/<key>` `{ value: any }`
