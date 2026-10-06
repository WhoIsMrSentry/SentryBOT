# Skill: Doc-Sync — Otomatik Döküman Senkronizasyonu

> **Kalıcı Kural:** Bu projede herhangi bir modülün koduna dokunulduğunda, refactor yapıldığında, sınıf/fonksiyon/parametre eklendiğinde veya API değiştirildiğinde; ilgili modülün teknik dökümantasyonu (`README.md` ve `architecture_<modul>.md`) ile Mermaid diyagramları kodla eşzamanlı olarak güncellenir. Döküman asla kodun gerisinde bırakılamaz.

---

## 🎯 Temel İlkeler

1. **Eşzamanlılık (Atomic Updates):**
   - Kod değişikliği ve dökümantasyon güncellemesi aynı iterasyon/görev içerisinde ayrılmaz bir bütün olarak icra edilir.
   - Kod refactor edildiğinde testler çalıştırılır ve ardından döküman kodu yansıtacak şekilde anında güncellenir.

2. **Dökümantasyon Standartları:**
   - **Modülün Amacı & Sorumluluk Sınırları:** Tek Sorumluluk Prensibi (SRP) çerçevesinde modülün görevi net olarak tanımlanır.
   - **Görsel Mermaid Diyagramları:** Mimari akışı (`flowchart TD/LR`) veya zaman sıralamasını (`sequenceDiagram`) gösteren güncel diyagramlar yer alır.
   - **Bileşen Detayları & İmzalar:** Sınıflar, metotlar, parametreler, dönüş tipleri ve kritik iş kuralları (business logic) kodla %100 uyumlu olarak listelenir.
   - **Hata Yönetimi & Edge-Caseler:** Modülün karşılayabileceği istisnalar, fallback stratejileri ve güvenlik önlemleri açıklanır.
   - **Girdi/Çıktı & Modüller Arası Bağımlılıklar:** REST endpointleri, event bus yayınları/abonelikleri, donanım veya gateway ilişkileri belirtilir.

3. **Eski/Çürümüş Döküman Temizliği:**
   - Kod tabanında artık geçerli olmayan, silinmiş fonksiyonları veya eski sürümleri referans gösteren bayat açıklamalar temizlenir, dökümantasyon tek gerçek kaynak (Single Source of Truth) kod ile uyumlu tutulur.
