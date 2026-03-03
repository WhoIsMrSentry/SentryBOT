# Sentry Persona Komut Testleri

Bu dosya, Sentry persona instruction'ının üreteceği action tiplerini hızlı doğrulama için örnek istemler içerir.

## 1) Speech kontrol
İstem: "Dinlemeyi durdur ve sonra tekrar başlat"
Beklenen action örnekleri:
- {"type":"system","attrs":{"module":"speech","action":"stop"}}
- {"type":"system","attrs":{"module":"speech","action":"start"}}

## 2) Wakeword kontrol
İstem: "Wakeword kapat"
Beklenen:
- {"type":"system","attrs":{"module":"wakeword","action":"stop"}}

## 3) OLED yüz
İstem: "Ekranda surprised yüzünü göster"
Beklenen:
- {"type":"oled","attrs":{"action":"show","name":"surprised"}}

## 4) OLED animasyon
İstem: "Ekranda scan animasyonunu başlat"
Beklenen:
- {"type":"oled","attrs":{"action":"anim","name":"scan"}}

## 5) Donanım karma
İstem: "Lazerleri kapat, kısa bir beep at, sonra blink yap"
Beklenen:
- {"type":"laser","attrs":{"on":false}}
- {"type":"buzzer","attrs":{"out":"loud","freq":2200,"ms":60}}
- {"type":"anim","attrs":{"name":"blink"}}

## 6) Raw Arduino passthrough
İstem: "Kafayı sola çevir ve track komutu gönder"
Beklenen:
- {"type":"arduino","attrs":{"cmd":"track","head_pan":70,"head_tilt":90,"drive":0}}

## 7) Event/mode
İstem: "Guardian moda geç ve olay bildir"
Beklenen:
- {"type":"mode","attrs":{"name":"guardian"}}
- {"type":"event","attrs":{"type":"persona.guardian"}}

## Doğrulama Kriteri
- Çıktı tek JSON obje olmalı.
- text/thoughts/actions boş olmamalı.
- action tipleri instruction içindeki whitelist dışına çıkmamalı.
