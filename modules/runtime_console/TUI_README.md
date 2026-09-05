# SentryBOT TUI Control Center

Robotu tek terminal ekranında izlemek ve temel ayarları yönetmek için TUI v2 kullanılır.

## Başlatma

Robotu TUI içinde başlatmak:

```cmd
.\.venv\Scripts\python.exe apps\run_robot_tui.py
```

Çalışan robota/loglara bağlanmak:

```cmd
.\.venv\Scripts\python.exe apps\sentrybot_tui.py
```

Birleşik giriş: kök `sentrybot.py`.

## Sekmeler

`modules/runtime_console/services/models.py` `TABS` ile aynı sıra:

1. Overview
2. Logs
3. Signals
4. Config
5. Search
6. Companion
7. Expression
8. Camera
9. Help

## Tuşlar

- `1..9`: sekme değiştir
- `/`: arama filtresi
- `c`: aramayı temizle
- `r`: yenile
- `Up/Down`: kaydırma
- `q`: çık

HTTP kuyruğu gateway `include.runtime_console=true` iken `/runtime_console/healthz` ve `/events` altındadır.
