# SentryBOT — Claude Code Entry Point

**Tek merkez:** `.sentrybot/AI_HUB.md`

Tüm agent, skill, context, sub-agent ve Obsidian notları `.sentrybot/` dizininde toplanmıştır.
Bir göreve başlamadan önce `.sentrybot/AI_HUB.md` dosyasını oku.

## Sık kullanılan komutlar
```bash
python -m pytest modules/ -q --maxfail=1
python -m pytest modules/<mod>/tests/ -v
python run_robot.py
python3 .sentrybot/tools/generate_module_ai_assets.py  # modül AI varlıklarını yenile
```
