# Gateway Module

Tek FastAPI sürecinde tüm modül router’larını orkestre eden ana giriş kapısı. Üretimde tek porttan hizmet verir.

## Çalıştırma
```bash
python -m modules.gateway.xGatewayService
```

## Konfig
`modules/gateway/config/config.yml`
- server.host / server.port
- include.<module>: true/false (arduino, vision_bridge, neopixel, interactions, speak, speech, ollama, wiki_rag, camera)

Varsayılan: tüm modüller açık (include=true).

## Uç Noktalar (özet)
- /arduino/*  – NDJSON seri köprü (hello, get_state, telemetry, …)
- /vision/track – Dış işlemciden baş/drive komutu köprüsü
- /neopixel/* – LED efektleri/emotions
- /interactions/* – Kural motoru (NeoPixel tetikleme)
- /speak/* – TTS
- /speech/* – ASR/DoA API’leri
- /ollama/* – LLM sohbet/persona
- /wiki_rag/* – Yerel RAG
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

## Notlar
- Modüller bağımsız servis olarak da çalışabilir, ancak gateway üretim modudur.
- Gateway modeli Pi5’te süreç sayısını azaltır; ortak log/limit kolaydır.
