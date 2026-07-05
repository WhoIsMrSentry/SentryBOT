# Sub-Agent: social_db-specialist

## Uzmanlık
`SocialDB` ve `social_db` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/social_db.md`

## Bileşen haritası
- `SocialDB` — Aggregates SQLite repositories for the social/identity domain.

## Dış bağlantılar (neden)
- —

## Gelen bağlantılar (neden)
- [[agent_core]] (import): Kullanıcı/tanıma verisi için sosyal hafızayı kullanır.
- [[agent_core]] (import): Kullanıcı/tanıma verisi için sosyal hafızayı kullanır.
- [[autonomy]] (import): Kişi hafızası ve ilişki seviyelerini okur/günceller.
- [[autonomy]] (import): Kişi hafızası ve ilişki seviyelerini okur/günceller.
- [[autonomy]] (import): Kişi hafızası ve ilişki seviyelerini okur/günceller.
- [[config_center]] (import): `config_center` kod içinde `social_db` modülünü import eder (`get_default`) — SQLite kişi hafızası, ilişki/tanıma seviyeleri.
- [[config_center]] (import): `config_center` kod içinde `social_db` modülünü import eder (`db`) — SQLite kişi hafızası, ilişki/tanıma seviyeleri.
- [[gateway]] (import): `gateway` kod içinde `social_db` modülünü import eder (`config_loader`) — SQLite kişi hafızası, ilişki/tanıma seviyeleri.
- [[gateway]] (import): `gateway` kod içinde `social_db` modülünü import eder (`db`) — SQLite kişi hafızası, ilişki/tanıma seviyeleri.
- [[interactions]] (import): `interactions` kod içinde `social_db` modülünü import eder (`get_default`) — SQLite kişi hafızası, ilişki/tanıma seviyeleri.
- [[vlm_bridge]] (import): Yüz tanıma sonuçlarını kişi kaydına yazar.
- [[vlm_bridge]] (import): Yüz tanıma sonuçlarını kişi kaydına yazar.
