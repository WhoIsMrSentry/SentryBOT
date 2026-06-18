# Sub-Agent: gateway-specialist

## Uzmanlık
`None` ve `gateway` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/gateway.md`

## Bileşen haritası
- —

## Dış bağlantılar (neden)
- [[admin_ui]] (import): `gateway` içinde `api` import edilir; `admin_ui` modülünün yeteneğini kullanır (Web yönetim paneli (statik dosyalar)).
- [[admin_ui]] (import): `gateway` içinde `config_loader` import edilir; `admin_ui` modülünün yeteneğini kullanır (Web yönetim paneli (statik dosyalar)).
- [[agent_core]] (http): `gateway` HTTP ile `agent_core` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[agent_core]] (http): `gateway` HTTP ile `agent_core` modülüne erişir: Ajan orkestrasyonu ve tool-calling çağrısı.
- [[agent_core]] (import): `gateway` içinde `api` import edilir; `agent_core` modülünün yeteneğini kullanır (3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling).
- [[agent_core]] (import): `gateway` içinde `services` import edilir; `agent_core` modülünün yeteneğini kullanır (3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling).
- [[animate]] (http): `gateway` HTTP ile `animate` modülüne erişir: YAML tabanlı servo animasyonu başlatır.
- [[animate]] (import): `gateway` içinde `xAnimateService` import edilir; `animate` modülünün yeteneğini kullanır (YAML servo animasyon oynatıcı).
- [[animate]] (import): `gateway` içinde `api` import edilir; `animate` modülünün yeteneğini kullanır (YAML servo animasyon oynatıcı).
- [[arduino_serial]] (arduino): Tüm /arduino/* isteklerini serial modüle proxy eder.
- [[arduino_serial]] (http): Tüm /arduino/* isteklerini serial modüle proxy eder.
- [[arduino_serial]] (http): Tüm /arduino/* isteklerini serial modüle proxy eder.

## Gelen bağlantılar (neden)
- [[admin_ui]] (mount): Tek port üzerinden tüm modül API'lerine erişir.
- [[admin_ui]] (registry): Tek port üzerinden tüm modül API'lerine erişir.
- [[agent_core]] (import): `agent_core` kod içinde `gateway` modülünü import eder (`url`) — FastAPI API bootstrapper, tüm modülleri mount eder.
- [[agent_core]] (mount): `agent_core` modülünün FastAPI router'ı gateway (8080) üzerinden tek portta dış dünyaya açılır.
- [[animate]] (mount): `animate` modülünün FastAPI router'ı gateway (8080) üzerinden tek portta dış dünyaya açılır.
- [[arduino_serial]] (mount): `arduino_serial` modülünün FastAPI router'ı gateway (8080) üzerinden tek portta dış dünyaya açılır.
- [[autonomy]] (import): `autonomy` kod içinde `gateway` modülünü import eder (`url`) — FastAPI API bootstrapper, tüm modülleri mount eder.
- [[autonomy]] (mount): `autonomy` modülünün FastAPI router'ı gateway (8080) üzerinden tek portta dış dünyaya açılır.
- [[calibration]] (mount): `calibration` modülünün FastAPI router'ı gateway (8080) üzerinden tek portta dış dünyaya açılır.
- [[camera]] (mount): `camera` modülünün FastAPI router'ı gateway (8080) üzerinden tek portta dış dünyaya açılır.
- [[common]] (import): `common` kod içinde `gateway` modülünü import eder (`url`) — FastAPI API bootstrapper, tüm modülleri mount eder.
- [[common]] (mount): `common` modülünün FastAPI router'ı gateway (8080) üzerinden tek portta dış dünyaya açılır.
