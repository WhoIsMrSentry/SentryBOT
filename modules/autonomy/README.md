# Autonomy Module
 
 Bu modül, robotun "Live Mode" (Canlı Mod) davranışlarını yönetir. Robotun kendi kendine kararlar almasını, çevresine tepki vermesini ve bir "kişilik" sergilemesini sağlar.
 
 ## Özellikler
 - **Davranış Döngüsü (Behavior Loop):** Sürekli çalışan ve ne yapılması gerektiğine karar veren ana döngü.
 - **İç Durum (Internal State):** Mutluluk, Enerji, Merak, Korku gibi değişkenleri yöneten `MoodManager`.
 - **Algı Birleştirme (Perception Aggregation):** Mikrofon (yön ve metin) verilerini sürekli tarar (`_sense`).
 - **Görsel Farkındalık:** Vision Bridge sonuçlarını periyodik olarak çekerek ortamda bir kişi/nesne belirdiğinde merak ve mutluluğu günceller, gerekiyorsa kişi ile sohbet başlatır.
 - **Canlılık Belirtileri:**
   - **Mikro-hareketler:** Nefes alma benzeri küçük servo hareketleri.
   - **Ses Takibi:** Ses gelen yöne otomatik kafa çevirme.
   - **Sıkılma:** Boşta kaldığında etrafı izleme, iç çekme veya monolog yapma.
 - **Duygu Yayını:** `MoodManager` dominant duyguyu `state_manager` ve `interactions` modüllerine aktararak LED/palet ve diğer istemcilerle paylaşıyor.
 - **Ses Tonu Çeşitliliği:** Mutluluk, yorgunluk, merak gibi duygulara göre TTS hız/volüm parametreleri otomatik ayarlanır; aynı cümle farklı ruh hâliyle söylenebilir.
 - **Zaman Çizgisi Hafızası:** Gün boyunca kişi ve sohbet sayılarını, ilginç soruları kaydeder; uykuya geçmeden önce kısa bir sözlü özet paylaşır.
 - **Dinamik Odak:** Vision Bridge yeni bir hareket/yüz gördüğünde kısa “focus” animasyonu ve LED olayı tetikler; animasyon servisi yoksa servo tabanlı küçük jest yapılır.
 - **Sahip Koruması:** `owner` konfigürasyonu aktifken robot esnek hitap biçimleriyle (Baba / Emir / WhoIsMrSentry) konuşur, sahibi görüşte değilse istekleri reddeder, RFID veya sözlü izin gelirse kısıtlamaları kaldırır, ısrarcı kişileri rapor eder, gerekirse geçici sahip atar ve Baba’yı aramak için kafasını sağ/sol tarar.
 - **LLM Karar Mekanizması:** Karmaşık durumlar için Ollama kullanarak karar verir.
 - **Animasyon Entegrasyonu:** Uygun olduğunda `animate` servisine hazır sekanslar gönderir, servis yoksa servo tabanlı fallback çalışır.
 
 ## Yapı
 - `xAutonomyService.py`: Servis başlatıcı.
 - `services/brain.py`: Ana karar mekanizması, duyular ve davranışlar.
 - `services/mood.py`: Duygu durum yönetimi (decay ve update mantığı).
  - `services/client.py`: Diğer modüllerle (Speech, Vision, Arduino, Interactions, State Manager) iletişim.

## Konfigürasyon
- `config/config.yml > endpoints`: Gateway üzerindeki servis URL’leri. Yeni varsayılanlar Speech, Interactions, State Manager ve Animate’i de içerir.
- `vision_hooks`: Vision Bridge entegrasyonu için periyot, kişi cooldown ve metin üretim ayarları.
  - `poll_interval_s`: Son sonuçların ne kadar sıklıkla okunacağı.
  - `person_cooldown_s`: Aynı kişi için tekrar selamlama gecikmesi.
  - `prefer_llm_greetings`: Tanınan kişilere kısa selamlama üretirken Ollama kullanılacak mı.
  - `speak_on_unknown`: `Unknown` kişilere de sözlü tepki ver.
- `owner`: Sahip kimliği ve güvenlik davranışları.
  - `addressing.affectionate|formal|handle` farklı bağlamlarda kullanılacak hitapları belirler.
  - `require_presence` true ise sahibi görülmeyince dış istekler reddedilir, `permission_grace_s` ile sözlü izin verilirse belirli süre boyunca uzak mod serbest bırakılır.
  - `restricted_keywords` hassas komutları listeler; Baba ortada yoksa veya yalnızca geçici sahip aktifse bu isteklere cevap verilmez.
  - `temporary` bloğu “`<isim> geçici sahip`” komutunu işler, süre (`duration_s`), tetiklenecek animasyon ve kapalı tutulacak özellikleri tanımlar. Sahip geri döndüğünde veya RFID onaylandığında geçici yetkiler sıfırlanır.
  - `rfid.endpoint` yetkilendirme API’sini gösterir; Gateway varsayılanı `http://localhost:8080/arduino/rfid/authorize` olup Arduino seri servisi son kart UID’sini kontrol eder ve `{"authorized": true}` dönerse `grace_s` kadar süreyle tüm kısıtlamalar açılır.

### Sahip Komutları (Örnek)
- **Geçici sahip ata:** “`Ali adlı kişi geçici sahip`” → Ali’ye sınırlı yetki verilir.
- **Geçici yetki iptal:** “`Geçici yetki iptal`” → aktif geçici sahip temizlenir.
- **Uzak izin:** “`Sana izin veriyorum, cevap verebilirsin`” → `permission_grace_s` süresince Baba görünmese de sorulara yanıt verir.
