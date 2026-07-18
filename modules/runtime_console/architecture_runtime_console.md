# runtime_console

ASCII tabanli, logosuz SentryBOT terminal katmani.

Amaç:
- Teknik log gürültüsünü azaltmak
- VLM/kamera/konuşma/TTS olaylarini ayirt edilebilir göstermek
- Dosya loglarini tam detayli tutarken terminali kullanici dostu yapmak
- Logo veya maskot ASCII sanati göstermemek

Ana parçalar:
- `RuntimeConsoleLogHandler`: logging handler olarak calisir
- `RuntimeEventBus`: ortak runtime olay hafizasi
- `ConsoleRenderer`: kutu, chip ve progress render yardimcilari
- `panels.py`: event/warning/system panelleri

Git komutu veya harici bagimlilik kullanmaz.
