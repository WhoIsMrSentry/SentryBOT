# Autonomy Module
 
 Bu modül, robotun "Live Mode" (Canlı Mod) davranışlarını yönetir. Robotun kendi kendine kararlar almasını, çevresine tepki vermesini ve bir "kişilik" sergilemesini sağlar.
 
 ## Özellikler
 - **Davranış Döngüsü (Behavior Loop):** Sürekli çalışan ve ne yapılması gerektiğine karar veren ana döngü.
 - **İç Durum (Internal State):** Mutluluk, Enerji, Merak, Korku gibi değişkenleri yöneten `MoodManager`.
 - **Algı Birleştirme (Perception Aggregation):** Mikrofon (yön ve metin) verilerini sürekli tarar (`_sense`).
 - **Görsel Farkındalık:** Vision Bridge sonuçlarını periyodik olarak çekerek ortamda bir kişi/nesne belirdiğinde merak ve mutluluğu günceller, gerekiyorsa kişi ile sohbet başlatır.
 - **Canlılık Belirtileri:**
  - **Mikro-hareketler:** Duyguya göre değişen küçük servo hareketleri (joy daha enerjik, tired daha sakin).
   - **Ses Takibi:** Ses gelen yöne otomatik kafa çevirme.
   - **Sıkılma:** Boşta kaldığında etrafı izleme, iç çekme veya monolog yapma.
  - **Idle Behavior Tree:** Boşta kalınca ağırlıklı davranış ağacı ile `look_around/blink/stretch/sigh/monologue` seçimi.
  - **Scene Orchestration:** Konuşma + ışık + hareket tek sahne akışında senkron yürütülür (özellikle vision selamlamaları).
 - **Duygu Yayını:** `MoodManager` (HAPPINESS, ENERGY, CURIOSITY, FEAR) dominant duyguyu `state_manager` ve `interactions` modüllerine aktararak LED/palet ve diğer istemcilerle paylaşıyor.
- **Duygusal Işık Senkronizasyonu:** NeoPixel animasyonları artık robotun dominant duygusuna göre (`joy`, `sadness`, `fear` vb.) otomatik renk seçimi yapabiliyor.
- **Sistem-Genel Modül Kontrolü:** Ollama üzerinden gelen `system` aksiyonları ile `notifier`, `camera` gibi modüller çalışma esnasında durdurulup başlatılabilir.
- **Ses Tonu Çeşitliliği:** Mutluluk, yorgunluk, merak gibi duygulara göre TTS hız/volüm parametreleri otomatik ayarlanır.
- **Gece Konuşma Kısma:** Quiet-hours sırasında konuşma tonu otomatik olarak sakin moda alınır ve çok uzun cümleler kısaltılır.
 - **Zaman Çizgisi Hafızası:** Gün boyunca kişi ve sohbet sayılarını, ilginç soruları kaydeder; uykuya geçmeden önce kısa bir sözlü özet paylaşır.
 - **Dinamik Odak:** Vision Bridge yeni bir hareket/yüz gördüğünde kısa “focus” animasyonu ve LED olayı tetikler; animasyon servisi yoksa servo tabanlı küçük jest yapılır.
 - **Sahip Koruması:** `owner` konfigürasyonu aktifken robot esnek hitap biçimleriyle (Baba / Emir / WhoIsMrSentry) konuşur, sahibi görüşte değilse istekleri reddeder, RFID veya sözlü izin gelirse kısıtlamaları kaldırır, ısrarcı kişileri rapor eder, gerekirse geçici sahip atar ve Baba’yı aramak için kafasını sağ/sol tarar.
 - **LLM Karar Mekanizması:** Karmaşık durumlar için Ollama kullanarak karar verir.
 - **Animasyon Entegrasyonu:** Uygun olduğunda `animate` servisine hazır sekanslar gönderir, servis yoksa servo tabanlı fallback çalışır.
- **LLM Eylem İşleme:** Ollama'dan gelen yapılandırılmış JSON aksiyonları veya `[cmd:*]` etiketleri `ResponseTagMixin` ile çözümlenip donanım/sistem katmanına yönlendirilir.
 
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
- `speech_quiet_hours`: Gece konuşma davranışı.
  - `enabled`: true ise etkin.
  - `start` / `end`: `HH:MM` formatında saat aralığı.
  - `tone`: konuşma isteğine tone verilmemişse varsayılan ton.
  - `max_chars`: konuşma metni üst sınırı (uzun metinler kısaltılır).
  - `prefix`: istenirse metin başına eklenecek kısa önek.
- `behaviors.idle_tree`: Boşta davranış planlayıcısı.
  - `enabled`: etkin/pasif.
  - `interval_s`: iki idle aksiyon arasındaki minimum aralık.
  - `fallback_to_llm`: planner uygun aksiyon bulamazsa LLM kararına düş.
  - `path`: idle davranış YAML dosyası yolu.
- `defaults.body_language.profiles`: dominant emotion -> mikro hareket profili (`pan_delta`, `tilt_delta`, `event`).
- `scenes`: Çok adımlı sahne tanımları (`event/effect/base/anim/head/speak/sleep`).
  - Varsayılan: `vision_greeting_known`, `vision_greeting_unknown`.
  - Segment adımları: `segment_fill` ve `segment_anim` ile göz/gövde ayrık tepkiler.
- `offline_mode`: LLM/RAG servisi geçici erişilemezse yerel fallback yanıtları.
  - `enabled`: etkin/pasif.
  - `availability_ttl_s`: servis erişilebilirlik sonucu kaç saniye cache edilecek.
  - `fallback_replies`: çevrimdışı durumda konuşulacak kısa cümleler.
  - `persona_replies`: dominant duyguya göre çevrimdışı cümle havuzu.

- `vision_hooks.focus`: vision odak jitter azaltma.
  - `jitter_min` / `jitter_max`: rastgele pan sapma aralığı.
  - `deadband_deg`: çok küçük hareketleri atla.
  - `smoothing`: hedef pan geçişini yumuşatma katsayısı.
- `vision_hooks.dynamic_cooldown`: mesafeye göre kişi tekrar selamlama cooldown'u.
  - Yakın kişilerde daha hızlı, uzak kişilerde daha yavaş tekrar selamlama.

- Cinematic scene seçimi:
  - owner -> `vision_greeting_owner`
  - known & close -> `vision_greeting_known_close`
  - known -> `vision_greeting_known`
  - unknown & close -> `vision_greeting_unknown_close`
  - unknown -> `vision_greeting_unknown`

### Idle Behavior Dosyası
`modules/autonomy/config/idle_behaviors.yml` içinde her aksiyon için ağırlık ve cooldown tanımlanır:

```yaml
actions:
  - name: LOOK_AROUND
    weight: 5
    min_interval_s: 6
  - name: MONOLOGUE
    weight: 1
    min_interval_s: 28
```

### Scene Örneği
`config.yml` içinde:

```yaml
scenes:
  vision_greeting_known:
    steps:
      - { type: effect, name: "COMET", duration_ms: 700 }
      - { type: anim, name: "vision_focus" }
      - { type: speak, text: "{greeting}", emotion: "joy" }
      - { type: base, name: "BREATHE", color: "#1E90FF" }
```

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
