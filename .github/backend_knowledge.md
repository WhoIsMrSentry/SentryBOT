# Backend Knowledge

SentryBOT backend, Raspberry Pi 5 üzerinde çalışan modüler FastAPI mikro-servis mimarisidir.

## Teknolojiler
- **Framework:** FastAPI (Python 3.10+)
- **LLM:** Ollama (qwen3.5:9b)
- **Veritabanı:** SQLite (social_db modülü)
- **İletişim:** HTTP (modüller arası), NDJSON Serial (Arduino ile)
- **Donanım:** Raspberry Pi 5, Arduino Mega

## Mimari
5 katman: Algı → Beyin → AI/RAG → Eylem → Arka Plan
Gateway (port 8080) tüm modülleri mount eder.

Detay: `.sentrybot/context/architecture-summary.md`
