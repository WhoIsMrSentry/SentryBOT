# Mutagen

Mutagen CLI tabanlı dosya senkronizasyonunu gateway üzerinden yönetir. Geliştirici makinesi ile robot (Pi) arasında iki yönlü kod eşitlemesi sağlar.

## Sorumluluklar

- Mutagen sync oturumu başlatma/durdurma
- Oturum durumu sorgulama (`mutagen sync list --json`)
- Zorunlu full rescan (`mutagen sync flush --all`)

## Mimari

- Giriş noktası: `xMutagenService.py`
- Runner: `services/runner.py` (`MutagenRunner`)
- Router: `api/router.py`

Gateway `_IMPORT_MODULES` ile `include.mutagen=true` olduğunda mount edilir. Mutagen CLI sistem PATH'inde olmalıdır.

## API (Gateway altında `/mutagen/*`)

- `GET /mutagen/healthz`
- `GET /mutagen/status`
- `POST /mutagen/start` — config'teki `pairs` için sync create
- `POST /mutagen/stop` — `mutagen sync terminate --all`
- `POST /mutagen/rescan` — `mutagen sync flush --all`

## Konfigürasyon

`config/config.yml`:
```yaml
mutagen:
  enabled: true
  pairs:
    - name: repo
      alpha: ..
      beta: /home/pi/SentryBOT
      mode: two-way-resolved
  opts:
    sync_mode: two-way-resolved
    ignore:
      - .git
      - __pycache__
      - "*.pyc"
```

## İlişkiler

- `ota`: firmware build artefaktları senkronu
- Geliştirme workflow'u; production otonomiye dahil değildir

SSH açmadan gateway üzerinden sync yönetimi sağlar.
