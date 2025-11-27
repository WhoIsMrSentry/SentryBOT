# Autonomy Module
 
 Bu modül, robotun "Live Mode" (Canlı Mod) davranışlarını yönetir. Robotun kendi kendine kararlar almasını, çevresine tepki vermesini ve bir "kişilik" sergilemesini sağlar.
 
 ## Özellikler
 - **Davranış Döngüsü (Behavior Loop):** Sürekli çalışan ve ne yapılması gerektiğine karar veren ana döngü.
 - **İç Durum (Internal State):** Mutluluk, Enerji, Merak, Korku gibi değişkenleri yöneten `MoodManager`.
 - **Algı Birleştirme (Perception Aggregation):** Mikrofon (yön ve metin) verilerini sürekli tarar (`_sense`).
 - **Canlılık Belirtileri:**
   - **Mikro-hareketler:** Nefes alma benzeri küçük servo hareketleri.
   - **Ses Takibi:** Ses gelen yöne otomatik kafa çevirme.
   - **Sıkılma:** Boşta kaldığında etrafı izleme, iç çekme veya monolog yapma.
 - **LLM Karar Mekanizması:** Karmaşık durumlar için Ollama kullanarak karar verir.
 
 ## Yapı
 - `xAutonomyService.py`: Servis başlatıcı.
 - `services/brain.py`: Ana karar mekanizması, duyular ve davranışlar.
 - `services/mood.py`: Duygu durum yönetimi (decay ve update mantığı).
 - `services/client.py`: Diğer modüllerle (Speech, Vision, Arduino) iletişim.
