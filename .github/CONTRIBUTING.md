# SentryBOT Icin Katki Rehberi

Katkiniz icin tesekkurler.
Bu proje moduler servis mimarisi ve DryCode prensiplerini izler.

## Baslamadan Once
- Tekrari onlemek icin mevcut issue ve pull requestleri kontrol edin.
- Yeni modul gelistirmeden once ilgili modulleri inceleyip desenleri tekrar kullanin.
- Degisiklikleri kucuk ve odakli tutun.

## Gelistirme Ortami
1. Depoyu klonlayin ve bir sanal ortam olusturun.
2. Bagimliliklari `install_all_requirements.py` veya `install_all_requirements.sh` ile kurun.
3. Gateway'i lokal calistirin:
   - `python run_robot.py`
4. Istege bagli VS Code gorevi:
   - `Run Gateway server (platform)`

## Branch ve Commit Kurallari
- `dev` dalindan yeni feature branch acin.
- Acik ve anlamli commit mesajlari kullanin.
- Ilgisiz degisiklikleri ayni pull requestte birlestirmeyin.

## Kodlama Kurallari
- DryCode uygulayin: tekrar etmeyin, kodu sade tutun.
- Dosyalar tek sorumluluk tasimali, fonksiyonlar kisa olmali.
- Her modul hem import edilebilir kutuphane hem calistirilabilir servis olmali.
- Varsayilanlar `config/config.yml` icinde olmali; runtime degerleri hardcode edilmemeli.
- Davranis degisiklikleri icin test ekleyin veya testleri guncelleyin.

## Arduino Komut Kontrati (Zorunlu)
Degisiklik Arduino'ya komut gonderiyorsa:
- `modules/arduino_serial/contract.py` icindeki builder yardimcilarini kullanin.
- Kontrat disinda elle `{"cmd": ...}` payload yazmayin.
- Kritik komutlarda (`set_servo`, `stepper`, `track`, `pid_*`) tercihen `/arduino/request` kullanin.
- Yeni komut ailesi eklerken dogrulama ve test guncellemesi ekleyin.

## Pull Request Kontrol Listesi
- [ ] Kod modul mimarisi ve DryCode kurallarina uyuyor.
- [ ] Konfig guncellemeleri modul `config/config.yml` dosyalarinda.
- [ ] Degisen davranis icin test eklendi/guncellendi.
- [ ] Dokumantasyon guncellendi (`README` veya modul dokumanlari).
- [ ] Uygunsa Arduino kontrat uyumu dogrulandi.

## Hata ve Ozellik Talebi
`.github/ISSUE_TEMPLATE` altindaki issue template'lerini kullanin.

## Guvenlik Konulari
Acik zafiyetler icin public issue acmayin.
Bildirim icin `SECURITY.md` belgesini izleyin.
