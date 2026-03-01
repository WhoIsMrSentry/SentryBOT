SentryBOT Arduino firmware — Test talimatları (Stepper PID & Hall)

Amaç
- Kapalı döngü (Hall) stepper PID kontrolünü güvenli şekilde doğrulamak, PID kazançlarını test etmek ve EEPROM'a kaydetme/geri yükleme işlevlerini doğrulamak.

Güvenlik Önlemleri (MUST)
1. Motor sürücülerin tahrik gücünü sınırlayın veya güç kaynağını düşük voltajda başlatın.
2. Fiziksel olarak tekerlekleri/şasi bağlantılarını sabitleyin; küçük hızlarda test edin.
3. `PIN_STEPPER_ENABLE` manuel olarak düşük seviyeye alınabilmesi için erişim sağlayın.
4. Eğer motor ısınır veya anormal davranış görülürse hemen güç kesip `pid_clear_stall` komutunu gönderin.

Seri Komutlar (NDJSON)
- Temel format: Tek satır JSON, örn: {"cmd":"pid_enable","id":0,"enable":true}
- Önemli komutlar:
  - `{"cmd":"pid_enable","id":<0|1>,"enable":true|false}`
  - `{"cmd":"pid_set","id":<0|1>,"kp":<float>,"ki":<float>,"kd":<float>,"target":<steps/s>}`
  - `{"cmd":"pid_status","id":<0|1>}` -> döner: {"ok":true,"id":0,"measured":<steps/s>,"target":<steps/s>,"stalled":true|false}
  - `{"cmd":"pid_save","id":<0|1>}`
  - `{"cmd":"pid_load","id":<0|1>}`
  - `{"cmd":"pid_clear_stall","id":<0|1>}`
  - `{"cmd":"stepper_cfg","maxSpeed":<float>,"accel":<float>}`
  - `{"cmd":"home"}` ve `{"cmd":"zero_now"}` için pozisyon testleri

Manuel hızlı test akışı
1. Seri bağlantıyı açın (ör: `Serial3` bağlıysa uygun USB-UART ile) ve baud: 115200.
2. PID'i etkinleştirin (düşük hedef hızla):
  {"cmd":"pid_enable","id":0,"enable":true}
  {"cmd":"pid_set","id":0,"kp":1.0,"ki":0.0,"kd":0.05,"target":20}
3. Durumu sorgulayın: {"cmd":"pid_status","id":0}
4. Hız artışı yaparken tekerleğin fiziksel davranışını gözleyin. Eğer `stalled:true` dönerse hemen `pid_clear_stall` gönderin ve fiziksel inceleme yapın.
5. Kazançlardan memnun kalırsanız EEPROM'a kaydedin: {"cmd":"pid_save","id":0}

Otomatik test (örnek Python script)
- Repository içinde `scripts/serial_stepper_test.py` örneği bulunmaktadır. Script:
  - Seri porttan komut gönderir,
  - Hedef hızları tarar (sweep),
  - Her adımda `pid_status` dönen ölçümü loglar (CSV).

Örnek komut (Windows PowerShell):
```powershell
python .\scripts\serial_stepper_test.py --port COM4 --baud 115200 --id 0 --start 10 --stop 200 --step 10 --log pid_log.csv
```

Log formatı (CSV)
- timestamp_ms,id,target,measured,stalled,raw
- Örnek satır: 1677661234567,0,50.0,48.3,false,{"cmd":"pid_status",...}

Notlar
- İlk testleri düşük hızlarda (<=100 steps/s) yapın.
- PID kazançları `xConfig.h` içindeki varsayılanlara ayarlı. Kalıcı kaydetme `pid_save` ile yapılır.