# SentryBOT — Claude Code Entry Point

SentryBOT, Raspberry Pi 5 üzerinde çalışan modüler bir otonom robot platformudur. 30 Python modülü, Arduino seri iletişim, OpenCV görüntü işleme ve Ollama LLM entegrasyonu içerir.

Tüm agent, skill, context, sub-agent ve Obsidian notları `.sentrybot/` dizininde toplanmıştır.
Bir göreve başlamadan önce `.sentrybot/AI_HUB.md` dosyasını oku.

## 📁 Tek Merkez: `.sentrybot/`

Tüm agent, skill, context ve template dosyaları **tek dizinde** toplanmıştır:

```
.sentrybot/
├── agents/          # 5 iş akışı yöneticisi
├── skills/          # 12 adım adım prosedür
├── context/         # Modül listesi, API haritası, mimari, kurallar
└── templates/       # Modül iskelet şablonları
```

### Görev Başlarken
1. `search_graph(label:"Module")` → 30+ modül (MCP) veya `get_architecture()`
2. `.sentrybot/context/conventions.md` → Tüm kurallar
3. İlgili agent dosyasını oku → İş akışını takip et
4. İlgili skill dosyalarını takip et → Adım adım uygula

### Sık Kullanılan Komutlar
```bash
python -m pytest modules/ -q --maxfail=1
python -m pytest modules/<mod>/tests/ -v
python run_robot.py
python3 .sentrybot/tools/generate_module_ai_assets.py  # modül AI varlıklarını yenile
```
