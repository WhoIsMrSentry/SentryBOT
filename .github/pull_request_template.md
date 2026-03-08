## Ozet
Ne degisti ve neden degisti?

## Degisiklik tipi
- [ ] Hata duzeltmesi
- [ ] Yeni ozellik
- [ ] Refactor
- [ ] Dokumantasyon guncellemesi
- [ ] Test guncellemesi

## Etkilenen moduller
Etkilenen yollari yazin (ornek: `modules/speech`, `modules/arduino_serial`).

## Dogrulama
- [ ] Lokal calistirma tamamlandi (`python run_robot.py` veya hedef modul calistirma)
- [ ] Ilgili testler geciyor
- [ ] Gerekli dokuman/konfig guncellemeleri yapildi

## Arduino Kontrat Kontrolu (uygunsa)
- [ ] `modules/arduino_serial/contract.py` disinda elle Arduino payload yazilmadi
- [ ] Kritik komutlar gerektiginde `/arduino/request` kullaniyor
- [ ] Yeni komut ailesi builder + validator + test iceriyor

## Risk ve geri alma
Olasi riskleri ve geri alma yaklasimini aciklayin.

## Ilgili issue
Closes #<issue-number>
