# State Manager

SentryBOT'un paylaşılan global durum deposudur. Modüller arası operasyonel durum, duygu listesi ve serbest anahtar/değer bilgilerini tek noktada tutar.

## Sorumluluklar

- Thread-safe durum okuma ve güncelleme
- `operational` ve `emotions` için kısa yol endpoint'leri
- İsteğe bağlı kalıcılık: `memory`, `json`, `sqlite`

## Mimari

- Giriş noktası: `xStateService.py`
- Router: `api/router.py`
- Depo implementasyonu: `services/store.py`
- Konfigürasyon: `config_loader.py`

`StateStore`, kilit korumalı bir sözlük üstüne kuruludur. Kalıcılık `sqlite` seçilirse `state` tablosuna, `json` seçilirse belirtilen dosyaya yazılır; `memory` modunda yalnızca süreç içi çalışır.

## API

Gateway altında `/state/*` olarak yayınlanır.

- `GET /state/healthz`
- `GET /state/get`
- `POST /state/set`
- `POST /state/set/operational`
- `POST /state/set/emotions`

## Konfigürasyon

Modül-içi `config/config.yml` kullanılır.

- `server.host`, `server.port`
- `defaults`
- `persistence.type`
- `persistence.path`

## İlişkiler

Bu modül, özellikle `autonomy` ve durum paylaşmak isteyen diğer servisler için merkezi bir veri yüzeyi sağlar. Mevcut kod tabanında pub/sub katmanı bulunmuyor; bu modül şu an için REST üstünden paylaşılan durum deposu rolünü yerine getiriyor.
