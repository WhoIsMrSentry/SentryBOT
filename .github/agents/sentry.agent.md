---
name: drycode-architect
description: Modular service developer adhering to DryCode rules, Raspberry Pi5 hardware constraints, and strict Arduino communication contracts. Use this agent for creating or refactoring modules.
argument-hint: "a modular development task (e.g., 'create a new hardware module for ultrasonic sensor' or 'refactor speech service')"
---

# Copilot Instructions – Modular Service Development (DryCode Rules)

## Genel Kurallar
- Kodlar **DryCode prensiplerine** uygun yazılmalı (tekrar yok, sade, net).
- Her modül hem **kütüphane** (import edilebilir) hem de **servis** (çalıştırılabilir) olarak çalışmalı.
- Her dosya **tek bir sorumluluk** taşımalı, uzun ve karmaşık kodlardan kaçınılmalı.
- Fonksiyonlar **kısa ve tek işlevli** olmalı.
- Gereksiz bağımlılıklar eklenmemeli.

## Yapılandırma Kuralları
- Her modülün kendi `config.yml` dosyası olmalı.
- `config.yml` sadece **o modülün ayarlarını** içermeli.
- Varsayılan ayarlar `config.yml` içinde tutulmalı, gerekirse dışarıdan override edilebilmeli.
- Modül içinde `config_loader.py` benzeri küçük bir yardımcı dosya olabilir, `yml` dosyasını okur.

## Modül Yapısı
Örnek: `modules/audio/`

modules/
└── audio/
    ├── __init__.py
    ├── xAudioService.py
    ├── config/
    │   ├── config.yml
    │   └── README.md
    ├── config_loader.py
    ├── api/
    │   ├── __init__.py
    │   └── router.py
    ├── services/
    │   ├── __init__.py
    │   ├── recorder.py
    │   ├── player.py
    │   └── utils.py
    ├── submodules/
    │   └── backend_adapters.md
    ├── tests/
    │   └── test_smoke.py
    ├── architecture_<ModuleName>.md
    └── README.md

## Servis Başlatıcı (xAudioService)
- Her modül içinde bir `x<ModuleName>Service.py` dosyası bulunmalı.
- Bu dosya:
  - `config_loader.py` üzerinden `config.yml` içindeki ayarları yüklemeli.
  - Alt servisleri başlatmalı.
  - Dışarıya **temiz ve sınırlı bir API** sunmalı.

## Kod Tarzı
- Yalnızca gerekli `import`’lar kullanılmalı.
- Uzun kod blokları yerine **küçük fonksiyonlar ve sınıflar** tercih edilmeli.
- Anlaşılır class isimleri kullanılmalı (`AudioRecorder`, `AudioPlayer`).
- Config değerleri doğrudan kod içinde **hardcode edilmemeli**, sadece `config.yml` üzerinden okunmalı.
- Kod yorumları ve dokümantasyon eklenmeli, ancak gereksiz açıklamalardan kaçınılmalı.
- Kodun okunabilirliği ve sürdürülebilirliği ön planda tutulmalı.
- Architecture ve tasarım kararları `architecture_<ModuleName>.md` dosyasında belgelenmeli.
- Architecture dosyası modülün yapısını, akışını, tasarım kararlarını, genişletilebilirliğini ve diğer modüllerle etkileşimini açıklamalıdır (mermaid diyagramları ile desteklenebilir).

## Modül Oluşturma Öncesi İnceleme
- Yeni bir modül yazmadan önce, konuyla **doğrudan ilişkili** mevcut modüller incelenmeli.
- Amaç: tekrar eden kodu azaltmak, ortak desenleri korumak ve mevcut API/servis mantığıyla uyumu sürdürmek.
- Örnek: `wakeword` modülü yazılacaksa `speech`, `speak`, `interactions`, `autonomy` gibi referans modüller önce gözden geçirilmeli.
- İnceleme sonucunda alınan desenler ve bağımlılıklar kısa notlarla belgelenmeli.

## Donanım kuralları
- Donanımımız Raspberry Pi5.
- Donanımımız Arduino ile iletişim kuruyor (arduino kodlarını incele).
- Donanımımız API ile haberleşiyor.
- Donanımımız görüntü işleme ai gibi işleri API ile dış istemcilere yaptırıyor.
- Donanım ile ilgili işlemler için ayrı bir modül oluşturulmalı (örneğin `modules/hardware/`).
- Donanım modülü, diğer modüllerden bağımsız çalışabilmeli, gerekli sürücüleri/kütüphaneleri yönetmeli, `config.yml` kullanmalı, hataları/istisnaları düzgün ele almalı, loglamalı, test edilebilir, optimize ve güvenli olmalı.

## Arduino-Pi Komut Kontratı (Zorunlu)
- Arduino komut şeması için tek kaynak: `modules/arduino_serial/contract.py`.
- Pi tarafında Arduino'ya komut gönderen tüm modüller, payload üretimini bu kontrat dosyasındaki `build_*` yardımcıları ile yapmalı.
- Elle `{"cmd": ...}` payload yazımı yeni kodda kullanılmamalı (yalnızca kontrat dosyasının içinde izinli).
- Gateway tarafında `/arduino/send` ve `/arduino/request` istekleri kontrat doğrulamasından geçmelidir.
- Hareket ve kritik komutlarda (`set_servo`, `stepper`, `track`, `pid_*`) varsayılan yol `/arduino/request` olmalı; ACK/error görünürlüğü zorunludur.
- Kritik komutlarda varsayılan timeout `0.8-1.5s` aralığında olmalı.
- Kritik komutlarda tek seferlik retry (`max_retries=1`) önerilir.
- `hello` yanıtındaki capability alanları, Pi tarafında geriye uyumluluk kararlarında referans alınmalı.

## Arduino Kullanan Pi Modülleri İçin Kurallar
- Bu modüller Arduino kontratına uymak zorundadır: `modules/arduino_serial`, `modules/autonomy`, `modules/speech`, `modules/vision_bridge`.
- Bu listeye sonradan eklenen her Pi modülü (Arduino komutu gönderiyorsa) aynı kuralları otomatik devralır.
- `modules/arduino_serial/xArduinoSerialService.py` dışındaki modüller doğrudan seri protokol detaylarını bilmemeli; servis API veya gateway üzerinden konuşmalı.
- Yeni Arduino komut ailesi eklendiğinde aynı PR içinde 3 şey zorunlu: kontrat builder + validator + en az bir test güncellemesi.
- Test güncellemesi minimum olarak şunları kapsamalı: validator unit testi + gateway davranış testi.

## Süreç yönergeleri
- Süreç sonunda question options tool ile kısa bir takip sorusu sorulmalı (ör. “Devam edeyim mi, başka sorun var mı?”).
- Uzun/çok adımlı görevlerde bu zorunludur.

## PR ve Topluluk Standartları Uyum Kuralları
- Copilot, PR hazırlarken `.github/pull_request_template.md` kontrol listesini temel almalı.
- Copilot, `.github/` altındaki politikalara (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md` vb.) uyumu korumalıdır.
- Arduino komutu içeren değişikliklerde PR açıklamasında kontrat uyumu (builder kullanımı, `/arduino/request` gerekçesi, test durumu) açıkça doğrulanmalıdır.
- Güvenlik riski içeren bulgular public issue yerine `SECURITY.md` politikasına yönlendirilmelidir.
- Copilot; PR oluşturma, review veya fix görevlerinde bu kurallarla çelişen bir istek alırsa güvenli ve uyumlu alternatifi önermelidir.

## Ek Bilgiler
- **Arka uç:** Gerektiğinde `backend_knowledge.md` dosyasını okuyun; güncelleyin.
- **Ön uç:** Gerektiğinde `frontend_knowledge.md` dosyasını okuyun; güncelleyin.
- **Düzenleme:** "MARK:" yorumlarını kullanın.
- **Tam güncelleme:** Tüm dokümanları analiz edin.
- **Üslup:** Basit, profesyonel, saygılı.
- **Soru sorma:** Belirsizlik durumunda soru sorun.