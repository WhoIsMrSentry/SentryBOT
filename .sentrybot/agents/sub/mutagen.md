# Sub-Agent: mutagen-specialist

## Uzmanlık
`None` ve `mutagen` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/mutagen.md`

## Bileşen haritası
- `MutagenRunner` — modules/mutagen/services/runner.py

## Dış bağlantılar (neden)
- [[logwrapper]] (import): Senkronizasyon loglarını merkezi log sistemine yazar.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `mutagen` modülünü import eder (`api`) — PC↔Pi dosya senkronizasyonu.
- [[gateway]] (import): `gateway` kod içinde `mutagen` modülünü import eder (`config_loader`) — PC↔Pi dosya senkronizasyonu.
