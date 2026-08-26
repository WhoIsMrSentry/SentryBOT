# Skill: expression

## Ana bileşen
- Sınıf: `xExpressionService` in `modules/expression/xExpressionService.py`
- Mission: LED/yüz ifade çıkışı (arbiter + renderer)

## API özeti
- `GET /expression/healthz`
- `POST /expression/express`

## Dış ilişkiler (neden)
- → [[neopixel]] / [[oled_faces]]: ifade render
- → [[interactions]]: olay köprüsü

## Gelen ilişkiler (neden)
- ← [[gateway]] (mount): `include.expression`
- ← [[autonomy]]: `express_emotion`

## Tam bilgi
`modules/expression/README.md`
