# SentryBOT TUI Control Center

Hedef: robotu htop/opencode benzeri tek ekranda izlemek ve temel ayarlarÄ± terminalden yÃ¶netmek.

## BaÅŸlatma

Robotu TUI iÃ§inde baÅŸlatmak:

```cmd
.\.venv\Scripts\python.exe apps\run_robot_tui.py
```

Sadece Ã§alÄ±ÅŸan robota/loglara baÄŸlanmak:

```cmd
.\.venv\Scripts\python.exe apps\sentrybot_tui.py
```

## Sekmeler

- `1 Overview`: servis saÄŸlÄ±k durumu ve ana engeller
- `2 Logs`: filtrelenebilir log kuyruÄŸu
- `3 Config`: YAML dosyalarÄ±nÄ± gÃ¶rÃ¼ntÃ¼leme ve nokta yoluyla dÃ¼zenleme
- `4 Search`: proje genelinde metin arama
- `5 Help`: kÄ±sayollar

## TuÅŸlar

- `1..5`: sekme deÄŸiÅŸtir
- `/`: arama filtresi gir
- `c`: aramayÄ± temizle
- `r`: yenile
- `Up/Down`: log kaydÄ±r veya config dosyasÄ± seÃ§
- `e`: seÃ§ili YAML dosyasÄ±nda dotted key dÃ¼zenle
- `q`: Ã§Ä±k

Config dÃ¼zenlemede dosya Ã¶nce `.sentrybot_backups` altÄ±na yedeklenir.
