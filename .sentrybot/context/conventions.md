# SentryBOT — Kod Kuralları ve Kalıplar (Conventions)

> Bu dosya tüm AI asistanlar tarafından kod yazarken uyulması gereken kuralları tanımlar.

## 1. DryCode Prensipleri

- **Tekrar yasak** — Aynı mantığı iki yere yazma, ortak util/helper çıkar.
- **Sade ve net** — Her dosya tek sorumluluk taşır, uzun fonksiyonlardan kaçın.
- **Kısa fonksiyonlar** — Her fonksiyon tek bir iş yapar, 30 satırı geçmez.
- **Gereksiz bağımlılık yasak** — Sadece gerçekten kullanılan kütüphaneleri ekle.

## 2. Modül Yapısı Kuralları

### 2.1 Dosya İsimlendirme
- Servis başlatıcı: `x<ModuleName>Service.py` (örn: `xSpeakService.py`)
- Config okuyucu: `config_loader.py`
- Config dosyası: `config/config.yml`
- API router: `api/router.py`
- Mimari doku: `architecture_<module_name>.md`

### 2.2 Çift Kullanım İlkesi
Her modül hem **kütüphane** (import edilebilir) hem de **servis** (bağımsız çalıştırılabilir) olarak çalışabilmelidir.

### 2.3 Config Kuralları
- Her modülün kendi `config/config.yml` dosyası olmalı.
- Config değerleri **asla hardcode** edilmez — sadece YAML'den okunur.
- Varsayılan ayarlar config.yml içindedir, çevre değişkenleriyle override edilebilir.
- `config_loader.py` dosyası YAML'i okur ve dict döndürür.

### 2.4 Modül Oluşturma Öncesi İnceleme
Yeni modül yazmadan önce mutlaka ilişkili mevcut modüller incelenmelidir:
- Amaç: Tekrarı azaltmak, ortak desenleri korumak
- Örnek: `wakeword` yazılacaksa → `speech`, `speak`, `interactions`, `autonomy` incelenir
- İnceleme sonuçları kısa notlarla belgelenir

## 3. Arduino Kontrat Kuralları (Zorunlu)

### 3.1 Tek Kaynak
Arduino komut şeması için tek kaynak: `modules/arduino_serial/contract.py`

### 3.2 Builder Zorunluluğu
Pi tarafında Arduino'ya komut gönderen tüm modüller, `contract.py`'deki `build_*` fonksiyonlarını kullanmalıdır. Elle `{"cmd": ...}` payload yazımı yasaktır.

### 3.3 İletişim Yolu
- Kritik komutlar (`set_servo`, `stepper`, `track`, `pid_*`) → `/arduino/request` (ACK beklenir)
- Kritik komut timeout: `0.8–1.5s` arası
- Tek seferlik retry `max_retries=1` önerilir

### 3.4 Yeni Komut Ekleme
Aynı PR'da 3 şey zorunlu:
1. `contract.py`'ye builder + validator
2. Validator unit testi
3. Gateway davranış testi

### 3.5 `hello` Uyumluluk
`hello.features` listesinde yoksa:
- Kritik komutlar → hard-fail
- Kozmetik komutlar → soft-skip + log

## 4. Kod Tarzı

```python
# ✅ İyi
from modules.arduino_serial.contract import build_set_servo

payload = build_set_servo(servo_id=1, angle=90)
await client.post("/arduino/request", json=payload)

# ❌ Kötü — elle payload
payload = {"cmd": "set_servo", "id": 1, "value": 90}
```

- Yalnızca gerekli `import`'lar kullanılır
- Anlaşılır class isimleri: `AudioRecorder`, `FaceDetector`, `MoodManager`
- Kod yorumları gerektiğinde eklenir, gereksiz açıklamalardan kaçınılır
- `# MARK:` yorumları VS Code navigasyonu için kullanılır

## 5. PR ve Topluluk Standartları

### 5.1 PR Şablonu
`.github/pull_request_template.md` kontrol listesi takip edilir:
- Değişiklik tipi (hata/özellik/refactor/dokümantasyon/test)
- Etkilenen modüller
- Lokal çalıştırma ve test onayı
- Arduino kontrat kontrolü (uygunsa)
- Risk ve geri alma planı

### 5.2 Topluluk Dosyaları
Bu dosyalara uyum zorunludur:
- `CODE_OF_CONDUCT.md` — Davranış kuralları
- `CONTRIBUTING.md` — Katkı kılavuzu
- `SECURITY.md` — Güvenlik politikası
- `ISSUE_TEMPLATE/` — Bug/Feature şablonları

### 5.3 Güvenlik
Güvenlik riski içeren bulgular → public issue **değil** → `SECURITY.md` private bildirim akışı

## 6. Donanım Kuralları

- Platform: **Raspberry Pi 5**
- Arduino ile NDJSON seri haberleşme
- Görüntü işleme/AI → API ile dış istemcilere devredilir
- Donanım modülleri bağımsız çalışabilmeli, hataları düzgün ele almalı, loglamalı
- `config.yml` üzerinden yapılandırılmalı

## 7. Test Kuralları

- Her modülde en az `tests/test_smoke.py` bulunmalı
- CI: `python -m pytest modules/ -q --maxfail=1`
- Python 3.10 hedef
- Donanım bağımlılıkları mock/stub ile test edilir
- WebRTC VAD, sounddevice gibi opsiyonel paketler CI'da uninstall edilir

## 8. Dokümantasyon Kuralları

- Merkezi mimari: `docs/ARCHITECTURE.md`
- Backend bilgisi: `.github/backend_knowledge.md`
- Frontend bilgisi: `.github/frontend_knowledge.md`
- Modül yerleşimi ve referans için kod tabanı MCP graph kullanılır; ayrı modül md notları zorunlu değildir.
