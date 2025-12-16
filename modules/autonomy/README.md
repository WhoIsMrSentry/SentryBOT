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
- **LLM Eylem Etiketleri:** Ollama, Wiki RAG veya Vision Bridge’den gelen `[cmd:*]` / `[[lights …]]` etiketleri `ResponseTagMixin` ile çözümlenip servo, animasyon, LED ve olay sistemlerine uygulanır. Dış istemciler `/autonomy/apply_actions` endpoint’ine POST ederek aynı yardımcıyı tetikleyebilir.
 
 ## Yapı
 - `xAutonomyService.py`: Servis başlatıcı.
 - `services/brain.py`: Ana karar mekanizması, duyular ve davranışlar.
 - `services/mood.py`: Duygu durum yönetimi (decay ve update mantığı).
  - `services/client.py`: Diğer modüllerle (Speech, Vision, Arduino, Interactions, State Manager) iletişim.
  - `services/palette_store.py`: LED paletlerini `config.yml` üzerinde atomik biçimde güncelleyen yardımcı.

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

### LED Palet Yönetimi
- **Config bloğu:** `defaults.lights.palettes` altında RGB listeleri tutulur. `lights.default_mode` ile LED animasyon fallback’i belirlenir.
- **REST API:**
  - `GET  /autonomy/lights/palettes` → Tüm paletler.
  - `POST /autonomy/lights/palettes/{name}` body `{ "rgb": [r,g,b] }` → Ekle/güncelle.
  - `DELETE /autonomy/lights/palettes/{name}` → Paleti sil.
  İstek sonrası `brain.update_palettes()` çağrısı sayesinde servis yeniden başlatmadan yeni renkler kullanılabilir.
- **CLI:** `python -m modules.autonomy.tools.palette_cli list|set|remove` ile aynı işlemler komut satırından yapılabilir. Örnek: `python -m modules.autonomy.tools.palette_cli set sunset --hex ff9933`.

### LLM Eylem Webhook’u
`/autonomy/apply_actions` endpoint’i `{ text, actions, raw, speak }` gövdesini kabul eder. `actions` içinde `commands` veya `blocks` alanları varsa `ResponseTagMixin` bu veriyi servo/palet/event katmanına yönlendirir, `speak=true` ise temizlenmiş metin aynı akışta TTS’ye gönderilir. Ollama, Wiki RAG ve Vision Bridge konfiglerinde `actions.default_apply: true` ayarı aktifleştirildiğinde yanıtlar otomatik olarak bu endpoint’e post edilir.

### Sahip Komutları (Örnek)
- **Geçici sahip ata:** “`Ali adlı kişi geçici sahip`” → Ali’ye sınırlı yetki verilir.
- **Geçici yetki iptal:** “`Geçici yetki iptal`” → aktif geçici sahip temizlenir.
- **Uzak izin:** “`Sana izin veriyorum, cevap verebilirsin`” → `permission_grace_s` süresince Baba görünmese de sorulara yanıt verir.
