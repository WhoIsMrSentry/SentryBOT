# Ollama Modülü Mimarisi

Ollama modülü (`modules/ollama`), robotun yerel LLM (Büyük Dil Modeli) ile olan tüm metinsel etkileşimlerini yönetir. Kişilik yapılandırmalarını uygular ve çıktıların donanım tarafından anlaşılabilecek (JSON) formatta üretilmesini garantiler.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Sohbetin nasıl gerçekleştiğini, sistem promptunun nasıl oluşturulduğunu ve yapılamayan/hatalı JSON formatlı çıktıların nasıl yedek (fallback) bir ayrıştırıcıya (`extract_llm_tags`) düştüğünü gösteren diyagram:

```mermaid
flowchart TD
    %% Ana Çağrı
    API_IN([POST /chat]) --> CHAT_MET[OllamaChatService.chat text, apply_actions]
    
    CHAT_MET --> GET_PERSONA[PersonaProvider.system_prompt name]
    GET_PERSONA --> CHK_PERSONA{Kişilik var mı?}
    
    CHK_PERSONA -- Hayır --> DEF_PERSONA[Varsayılan sentry seç]
    CHK_PERSONA -- Evet --> USE_PERSONA[Kişilik sistem metni al]
    
    USE_PERSONA --> GET_HIST[ChatMemory.get_context]
    DEF_PERSONA --> GET_HIST
    
    GET_HIST --> BLD_PROMPT{Mesajları Birleştir <br> System + History + User}
    
    BLD_PROMPT --> OLLAMA_API(OllamaClient.generate_json)
    
    %% Ollama API Yanıt Döngüsü
    subgraph Ollama_API [LLM İstek İşlemi]
        direction TB
        REQ[LLMe HTTP POST <br> format: json] --> RESP{HTTP 200 mü?}
        RESP -- Hayır --> ERR_RET([error: Failed to reach LLM])
        RESP -- Evet --> RAW_JSON(Yanıt Metni Al)
    end
    
    OLLAMA_API --> REQ
    RAW_JSON --> PARSE_JSON_P{Pydantic Modelle<br>JSON Parse Et}
    
    %% JSON Ayrıştırma Mantığı
    subgraph Parse_Logic [Çıktı Ayrıştırma if/else]
        direction TB
        PARSE_JSON_P -- Başarılı (Valid JSON) --> P_SUCCESS[text, thoughts, actions<br>değişkenlerini ata]
        PARSE_JSON_P -- Başarısız (Syntax Error) --> EXTRACT_TAGS[extract_llm_tags raw_text <br> Regex ile XML tagleri ara]
        
        EXTRACT_TAGS --> TAGS_RES[actions array oluştur]
        
        P_SUCCESS --> APPLY_ACT
        TAGS_RES --> APPLY_ACT
    end
    
    %% Etkileşim Kararı
    APPLY_ACT{apply_actions=True?}
    APPLY_ACT -- Hayır --> SAVE_MEM(ChatMemory.add_interaction)
    APPLY_ACT -- Evet --> HTTP_POST_BRAIN(POST /autonomy/apply_actions)
    
    SAVE_MEM --> RET_FINAL([API Yanıtı Döndür])
    HTTP_POST_BRAIN --> SAVE_MEM
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    OllamaChatService ||--|| PersonaProvider : reads
    OllamaChatService ||--|| ChatMemory : reads_writes
    OllamaChatService ||--|| OllamaClient : calls

    OllamaChatService {
        string current_persona
        bool apply_actions
    }
    PersonaProvider {
        string profile_source
        int profile_count
    }
    ChatMemory {
        int limit
        string last_user_message
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **`PersonaProvider.system_prompt(name)`**
   - **`if`** ilgili kişilik YAML dosyası mevcutsa (örn: `sentry.yml`), içerik okunup (isim, stil, kısıtlamalar) bir metne dönüştürülür.
   - **`else`**: Basit bir fallback "Sen bir asistansın" promptu döner.
2. **`OllamaClient` Bağlantısı Hata Yönetimi**
   - **`try/except`**: HTTP isteği sırasında sunucu kapalıysa veya zaman aşımı olursa (Ollama yüklü değilse), sistem çökmez, geriye `None` ve log bilgisi döner.
3. **Pydantic Fallback Sistemi**
   - LLM'ler her zaman düzgün JSON üretmeyebilir (özellikle küçük modeller).
   - **`if`** `json.loads(response)` patlarsa veya Pydantic model doğrulaması geçemezse:
     - Düz metin (`raw_text`) kabul edilir.
     - **`extract_llm_tags(text)`** modülü devreye girer. XML stili `<speak>...</speak>`, `<lights effect="breathe">...</lights>` etiketlerini `regex` (düzenli ifadeler) ile bulur ve bunları zorla `actions` JSON dizisine çevirir. Kalan metin `text` (kullanıcıya görünen) kısmı olur.
4. **`apply_actions` Kararı**
   - `chat` fonksiyonu çağrılırken `apply_actions=True` verilmişse (genelde Autonomy Brain yapıyor), Ollama modülü JSON çıktısını alıp doğrudan uygulamasını istemek için Autonomy servisine HTTP POST atar. Eğer `False` ise (sadece metin sorulmuşsa / API'den deneniyorsa) hiçbir motor hareketine dönüşmez, sadece metin döner.
