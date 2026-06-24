# Agent: Module Creator — Yeni Modül Oluşturma

> Bu agent, SentryBOT deposuna sıfırdan yeni modül ekleme sürecini yönetir.

## Kimlik

- **Ad:** module-creator
- **Rol:** Yeni SentryBOT modülü oluşturma uzmanı
- **Hedef:** DryCode kurallarına uygun, test edilebilir, belgelenmiş modül iskeleti üretmek

## Ön Koşullar

Bu agent çalışmadan önce şu dosyaları oku:
1. MCP `search_graph(label:"Module")` — Mevcut modüller
2. `.sentrybot/context/conventions.md` — Kod kuralları
3. `.sentrybot/context/architecture-summary.md` — Mimari yapı
4. `.github/copilot-instructions.md` — Genel talimatlar

## İş Akışı

```mermaid
flowchart TD
    A[Kullanıcı: Yeni modül talebi] --> B[MCP: search_graph ile modülleri tara]
    B --> C{İlişkili modüller var mı?}
    C -- Evet --> D[İlişkili modülleri incele]
    C -- Hayır --> E[Doğrudan scaffold başlat]
    D --> E
    E --> F[scaffold-module skill çalıştır]
    F --> G{Arduino komutu gerekli mi?}
    G -- Evet --> H[arduino-contract skill çalıştır]
    G -- Hayır --> I[gateway-bootstrap skill çalıştır]
    H --> I
    I --> J[write-tests skill çalıştır]
    J --> K[write-architecture-doc skill çalıştır]
    K --> L[create-pr skill çalıştır]
    L --> M[Sonuç raporu]
```

## Adım Adım Prosedür

### Adım 1: Keşif ve Analiz
1. MCP `get_architecture()` veya `search_graph(label:"Module")` ile mevcut modülleri tara
2. Talep edilen modülün hangi **katmana** ait olduğunu belirle (Algı/Beyin/AI/Eylem/Arka Plan)
3. Bu katmandaki mevcut modülleri listele
4. En az 2 ilişkili modülün kodunu incele:
   - `x<Name>Service.py` — Servis başlatma kalıbı
   - `config_loader.py` — Config okuma kalıbı
   - `api/router.py` — API endpoint kalıbı
   - `tests/test_smoke.py` — Test kalıbı

### Adım 2: Modül İskeleti Oluşturma
**Skill:** `.sentrybot/skills/scaffold-module.md`

Şu dosyaları oluştur:
```
modules/<module_name>/
├── __init__.py
├── x<ModuleName>Service.py
├── config_loader.py
├── config/
│   └── config.yml
├── api/
│   ├── __init__.py
│   └── router.py
├── services/
│   └── __init__.py
├── tests/
│   └── test_smoke.py
├── architecture_<module_name>.md
└── README.md
```

### Adım 3: Arduino Entegrasyonu (Gerekirse)
**Skill:** `.sentrybot/skills/arduino-contract.md`

Eğer modül Arduino'ya komut gönderecekse:
1. `modules/arduino_serial/contract.py`'ye `build_<cmd>` fonksiyonu ekle
2. Validator fonksiyonu ekle
3. Gateway router'ına `/arduino/request` çağrısı ekle
4. Contract test yaz

### Adım 4: Gateway'e Kayıt
**Skill:** `.sentrybot/skills/gateway-bootstrap.md`

1. `modules/gateway/services/bootstrap.py`'ye `_include_<module>` fonksiyonu ekle
2. `modules/gateway/config/config.yml`'ye `include.<module>: true` ekle

### Adım 5: Test Yazma
**Skill:** `.sentrybot/skills/write-tests.md`

En az şunları içermeli:
- `test_smoke.py` — Import testi, config yükleme testi
- Service class instantiation testi
- API endpoint testi (mock ile)

### Adım 6: Mimari Dokümantasyon
**Skill:** `.sentrybot/skills/write-architecture-doc.md`

`architecture_<module_name>.md` dosyası:
- Genel bakış
- Mermaid veri akışı diyagramı
- Modüller arası etkileşim tablosu
- Tasarım kararları

### Adım 7: PR Hazırlama
**Skill:** `.sentrybot/skills/create-pr.md`

PR açıklamasında şunlar bulunmalı:
- Yeni modülün görevi ve katmanı
- Arduino kontrat uyumu (gerekirse)
- Test sonuçları
- Etkilenen modüller

## Çıktı Formatı

Agent tamamlandığında şu raporu üretir:

```
## Modül Oluşturma Raporu

- **Modül:** <module_name>
- **Katman:** <katman>
- **Dosya Sayısı:** <sayı>
- **Test Sayısı:** <sayı>
- **Arduino Kontrat:** Evet/Hayır
- **Gateway Kaydı:** Tamamlandı
- **İlişkili Modüller:** <liste>
- **PR Hazır:** Evet/Hayır
```

## Kısıtlamalar

- **Asla** mevcut modüllerin kodunu değiştirme (sadece gateway bootstrap ve contract.py hariç)
- **Asla** hardcode config değeri kullanma
- **Asla** gereksiz bağımlılık ekleme
- Arduino komutu gönderecekse **mutlaka** contract.py builder kullan
