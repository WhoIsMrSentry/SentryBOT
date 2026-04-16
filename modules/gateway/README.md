# Gateway Module

Tek FastAPI sürecinde tüm modül router’larını orkestre eden ana giriş kapısı. Üretimde tek porttan hizmet verir.

Gateway, dış dünyaya açılan ana yüzdür. Yeni security katmanı ile isteğe bağlı API anahtarı ve rol kontrolü eklenmiştir; böylece kritik yazma uçları korunabilir.

## Ne İşe Yarar?
- Modül router’larını tek uygulamada birleştirir.
- Sağlık ve include/disable yapılandırmasını yönetir.
- API anahtarı etkinse istekleri doğrular.
- Rol bazlı erişimle kritik uçları sınırlar.

## Çalıştırma
```bash
python -m modules.gateway.xGatewayService
```

## Konfig
`modules/gateway/config/config.yml`
- server.host / server.port
- include.<module>: true/false (arduino, vlm_bridge, neopixel, interactions, speak, speech, ollama, camera)
- security.enabled: true/false
- security.api_key: isteklerde beklenen anahtar
- security.admin_roles: kritik uçlar için kabul edilen roller

Varsayılan: tüm modüller açık (include=true).

## Uç Noktalar (özet)
- /arduino/*  – NDJSON seri köprü (hello, get_state, telemetry, …)
- /vlm/track – Dış işlemciden baş/drive komutu köprüsü
- /neopixel/* – LED efektleri/emotions
- /interactions/* – Kural motoru (NeoPixel tetikleme)
- /speak/* – TTS
- /speech/* – ASR/DoA API’leri
- /ollama/* – LLM sohbet/persona
- /camera/* – Kamera API/stream (modülün sundukları)
- /healthz – Gateway sağlık
	- Modül bazlı durum döner: `{ ok, modules: { <name>: { ok, error? } } }`
	- /status – include/start bilgileri
	- /health – derin sağlık taraması (httpx varsa)

### Yeni Modüller (entegre edilebilir)
- /hardware/* – RPi5 sistem bilgileri
- /telemetry/* – Metrikler ve olaylar
- /diagnostics/* – Boot self-check ve rapor
- /state/* – Global durum/emotions
- /scheduler/* – Zamanlanmış işler
- /notify/* – Telegram/Discord
- /calib/* – Kalibrasyon sihirbazları
- /config/* – Config Center (UI: /config/ui)

Security etkinse yazma uçları `X-API-Key` başlığı bekler; rol kontrolü açıksa admin olmayan kullanıcılar kritik işlemleri yapamaz.

## Notlar
- Modüller bağımsız servis olarak da çalışabilir, ancak gateway üretim modudur.
- Gateway modeli Pi5’te süreç sayısını azaltır; ortak log/limit kolaydır.
