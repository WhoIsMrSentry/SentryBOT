# Skill: runtime_console

## Ana bileşen
- Sınıf: TUI v2 in `modules/runtime_console/tui_v2.py`
- Mission: Operatör terminali; otonom karar üretmez

## API özeti
- `GET /runtime_console/healthz`
- `GET /runtime_console/events`

## Dış ilişkiler (neden)
- → [[gateway]] (HTTP snapshot)
- → [[logwrapper]] (TUI log handler)

## Gelen ilişkiler (neden)
- ← [[gateway]] (mount): `include.runtime_console`

## Tam bilgi
`modules/runtime_console/README.md`
