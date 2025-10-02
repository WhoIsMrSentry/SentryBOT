# Animate Module

YAML tabanlı servo animasyonları. Ana scriptler animasyon içermeyecek; sadece isimle çağırıp çalıştıracaksınız.

## Örnek
- `modules/animate/animations/sit.yml` animasyon dosyasını `xAnimateService.run('sit')` ile çalıştırın.

## Kullanım
```python
from modules.animate.xAnimateService import xAnimateService

anim = xAnimateService()  # Arduino serial otomatik başlatılır
anim.start()
anim.run('sit')
anim.stop()
```

## API (opsiyonel)
```python
from modules.animate.api.router import get_router
router = get_router(anim)
```

## Gateway ile Kullanım
Bu modül gateway üzerinden tek porttan sunulacak şekilde orkestrasyona dahil edilebilir. Varsayılan kurulumda gateway modül router’larını monte eder. Animasyon tetiklemeyi doğrudan Arduino `set_pose(duration_ms)` komutlarıyla yapan üst servisler (ör. teleop veya özel iş mantığı) gateway’de barınabilir.

## Şema
```yaml
name: sit
loop: false
steps:
  - pose: [90,110,60, 90,110,60, 90,90]
    duration_ms: 1200
  - pose: [90,110,60, 90,110,60, 90,90]
    hold_ms: 500
```
