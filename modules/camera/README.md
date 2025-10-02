# Camera Module

Pi5 üzerinde OpenCV/PiCamera2 tabanlı yakalama ve yayıncı. FastAPI router ile görüntüye erişim/stream sunar.

## Özellikler
- Otomatik backend seçimi (auto/picamera2/opencv)
- Kaynak: device index veya yol
- Çözünürlük/FPS/JPEG kalitesi ayarlanabilir
- Yayıncı: aboneler için son çerçeveyi saklar

## Gateway ile Kullanım
Gateway çalışırken kamera uygulaması `/camera/*` altında tek porttan sunulabilir (gateway config include.camera: true). Bu mod, görüntüyü sadece çıkış olarak sağlar; işleme PC’de yapılır.
