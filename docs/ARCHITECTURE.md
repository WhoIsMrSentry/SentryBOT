# SentryBOT — Uçtan Uca Mimari ve İş Akış Haritası

SentryBOT devasa ve dağıtık çalışan bir platformdur. Yazılım altyapısının sürdürülebilir olması için devasa tekil dokümanlar yerine, her modül spesifik kendi mimari, `if/else`, hata yakalama (try/catch) ve lokal veri akış detaylarını kendi klasöründe tutar.

Bu doküman, robotun **Büyük Resmini (Big Picture)** çizmek ve alt modüllerin dokümanlarına erişmek için bir **Merkez İstasyon** (Index) görevi görür.

---

## 🗂️ Modül İçerik (Mimari) Dosyaları

Aşağıdaki bağlantılara tıklayarak, her modülün kendi iç mantık yapısına (Flowchart'lar, Karar Ağaçları, Pydantic/JSON fallback yapıları) ulaşabilirsiniz:

| Modül Kategori | Bileşen Adı | Detaylı Mimari Dokümanı | Görevi |
|---------------|--------------|-------------------------|--------|
| **Çekirdek** | Gateway | [architecture_gateway.md](../modules/gateway/architecture_gateway.md) | Mikroservisleri ayaklandıran API Bootstrapper |
| | Autonomy (Brain) | [architecture_autonomy.md](../modules/autonomy/architecture_autonomy.md) | Sense-Think-Act döngüsü, duygu bozunması, LLM kararları |
| | Arduino Serial | [architecture_arduino_serial.md](../modules/arduino_serial/architecture_arduino_serial.md) | NDJSON seri haberleşme, port polling ve arka plan thread kuyruğu |
| **Görsel Algı** | VLM Bridge | [architecture_vlm_bridge.md](../modules/vlm_bridge/architecture_vlm_bridge.md) | OpenCV yüz algılama, ORB/FLANN eşleme ve CSRT takip |
| | Camera | [architecture_camera.md](../modules/camera/architecture_camera.md) | MJPEG publisher stream, düşme anı auto-recovery restart mekanizması |
| **Ses & Dil** | Speech | [architecture_speech.md](../modules/speech/architecture_speech.md) | Çok kanallı ASR, ses gelişi (DOA) yön hesaplama filtresi |
| | Wakeword | [architecture_wakeword.md](../modules/wakeword/architecture_wakeword.md) | Sürekli dinleme, trigger sleep/wake timer geçişleri |
| | Speak (TTS) | [architecture_speak.md](../modules/speak/architecture_speak.md) | Ton/duygu if (happy/sad) hız ayarlaması, Markdown Regex temizliği |
| | Ollama (LLM) | [architecture_ollama.md](../modules/ollama/architecture_ollama.md) | Pydantic JSON validate try/catch ve XML regex ayrıştırıcı fallback adımları |
| **Etkileşim** | Interactions | [architecture_interactions.md](../modules/interactions/architecture_interactions.md) | CPU temp, Ağ yükü kural motoru (Rule Engine önceliklendirmesi) |
| | NeoPixel | [architecture_neopixel.md](../modules/neopixel/architecture_neopixel.md) | 23 Duygu paleti random renk çözümleme, SPI vs Simulator donanım seçimi |
| | Animate | [architecture_animate.md](../modules/animate/architecture_animate.md) | YAML step parsing, duyguya göre speed hesaplama, thread tabanlı oynatma |
| | State Manager | [architecture_state_manager.md](../modules/state_manager/architecture_state_manager.md) | Thread-safe Mutex lock'lar veri ezmeyi (`copy.deepcopy`) engelleme |

*(Log, Notifier, Telemetry, Scheduler, OTA gibi basit yardımcı (utility) modüller mimari doküman gerektirmeyecek kadar sadedir, Gateway üzerinden API yansıtırlar).*

---

## 🌐 Üst Düzey Sistem Etkileşim ve Veri Akış Modeli (Kuşbakışı)

SentryBOT'un tüm yapısını birbirine bağlayan ağaç. Autonomy Brain sistemin kalbindedir. `if` okları sistemin neyi seçtiğini ifade eder.

```mermaid
flowchart LR
    subgraph LAYER_SENSE ["1. ALGI VE SENSOR KATMANI"]
        direction TB
        subgraph SG_CAMERA ["CAMERA Modülü"]
            direction TB
            %% Ana Thread
            CAMERA_START_THREAD([Kamera Capture Thread]) --> CAMERA_HW_INIT(Donanıma Bağlan: /dev/video0)
            
            CAMERA_HW_INIT --> CAMERA_CHK_HW{"Kamera Cihazı<br>Açıldı mı?"}
            
            CAMERA_CHK_HW -- Hayır --> CAMERA_LOG_ERR[Hata: Kamera Bulunamadı] --> CAMERA_RETRY_WAIT(Saniye Bekle, Tekrar Dene) --> CAMERA_HW_INIT
            CAMERA_CHK_HW -- Evet --> CAMERA_ENTER_LOOP[Okuma Döngüsüne Gir]
            
            %% Çerçeve / Frame Okuma Döngüsü
            subgraph Capture Loop [Sürekli Okuma Döngüsü]
            CAMERA_ENTER_LOOP --> CAMERA_GRAB_FRAME(Kareyi Kapat - read)
            
            CAMERA_GRAB_FRAME --> CAMERA_CHK_FRAME{"Kare Başarılı <br> Geldi mi?"}
            CAMERA_CHK_FRAME -- Hayır --> CAMERA_LOG_DROP[Uyarı: Frame Dropped] --> CAMERA_RECONN_HW(Cihazı Kapat / Yeniden Aç) --> CAMERA_ENTER_LOOP
            
            CAMERA_CHK_FRAME -- Evet --> CAMERA_FPS_THROTTLE{"Hedef FPS<br>Geçildi mi?"}
            CAMERA_FPS_THROTTLE -- Evet --> CAMERA_SKIP((Kareyi Atla)) --> CAMERA_GRAB_FRAME
            
            CAMERA_FPS_THROTTLE -- Hayır --> CAMERA_ENCODE_JPEG(CAMERA_JPEG Olarak Sıkıştır)
            end
            
            %% Frame Publishing
            subgraph Publisher CAMERA_API [Yayın Mekanizması]
            CAMERA_ENCODE_JPEG --> CAMERA_LOCK_VAR[CAMERA_MUTEX Kilidi Al]
            CAMERA_LOCK_VAR --> CAMERA_UPDATE_VAR{"global_frame değişkenini<br>güncelle"}
            CAMERA_UPDATE_VAR --> CAMERA_UNLOCK_VAR[CAMERA_MUTEX'i Bırak]
            CAMERA_UNLOCK_VAR --> CAMERA_SIGNAL_EVENT(Tüm bekleyen web<br>istemcilerine Event Yolla)
            end
            
            CAMERA_SIGNAL_EVENT --> CAMERA_GRAB_FRAME
            
            %% Web Stream İstemcileri
            CAMERA_API_REQ([CAMERA_GET /camera/stream]) --> CAMERA_WEB_LOOP[Sonsuz Yield Döngüsü]
            CAMERA_WEB_LOOP --> CAMERA_WAIT_EVT(Signal Bekle)
            CAMERA_WAIT_EVT --> CAMERA_READ_F(CAMERA_global_frame'i oku)
            CAMERA_READ_F --> CAMERA_SEND_F(CAMERA_HTTP Multi-part olarak Yolla) --> CAMERA_WEB_LOOP
        end
        subgraph SG_HARDWARE ["HARDWARE Modülü"]
            direction TB
            %% Veri Toplama Akışı
            HARDWARE_START("GET /hardware/info") --> HARDWARE_GET_CPU("psutil.cpu_percent")
            HARDWARE_GET_CPU --> HARDWARE_GET_RAM("psutil.virtual_memory")
            HARDWARE_GET_RAM --> HARDWARE_GET_TEMP("vcgencmd measure_temp")
            HARDWARE_GET_TEMP --> HARDWARE_GET_I2C("i2cdetect cihazlarını tara")
            
            HARDWARE_GET_I2C --> HARDWARE_CHK_THROTTLE{"Sistem<br>Throttle Yiyor mu?"}
            
            HARDWARE_CHK_THROTTLE -- "Evet (Under-voltage veya Overheat)" --> HARDWARE_SET_WARN("Uyarı: Besleme veya Soğutma Yetersiz")
            HARDWARE_CHK_THROTTLE -- "Hayır" --> HARDWARE_SET_OK("Sistem Normal")
            
            HARDWARE_SET_WARN --> HARDWARE_BUILD_JSON("JSON Birleştir")
            HARDWARE_SET_OK --> HARDWARE_BUILD_JSON
            HARDWARE_BUILD_JSON --> HARDWARE_RET_OK("Arayüze Gönder")
        end
        subgraph SG_SPEECH ["SPEECH Modülü"]
            direction TB
            %% Ana Giriş
            SPEECH_START([Mikrofon Dinleme Döngüsü]) --> SPEECH_CAPTURE_AUDIO[Ses Akışını Yakala]
            
            %% Ses Yönü Bulma
            subgraph SPEECH_Direction_Calculation ["Ses Yönü Tahmini"]
            SPEECH_CAPTURE_AUDIO --> SPEECH_CHK_DIR_SUPPORT{"Cihaz Çok Kanallı mı? <br> (Örn: ReSpeaker)"}
            SPEECH_CHK_DIR_SUPPORT -- Evet --> SPEECH_CALC_DOA(SPEECH_DOA - Direction of Arrival <br> Hesapla)
            SPEECH_CHK_DIR_SUPPORT -- Hayır --> SPEECH_SKIP_DIR[Varsayılan 0° / İleri]
            
            SPEECH_CALC_DOA --> SPEECH_SET_DIR_VAR[Global Ses Yönü Değişkenini<br>Güncelle]
            SPEECH_SKIP_DIR --> SPEECH_SET_DIR_VAR
            end
            
            %% Konuşma Tanıma
            subgraph SPEECH_Speech_Recognition ["Konuşma Tanıma ASR"]
            SPEECH_SET_DIR_VAR --> SPEECH_VAD_CHK{"Ses Var mı? <br> Voice Activity Detection"}
            
            SPEECH_VAD_CHK -- Hayır --> SESSİZLIK((Bekle)) --> SPEECH_CAPTURE_AUDIO
            SPEECH_VAD_CHK -- Evet --> SPEECH_SEND_ASR[Ses Verisini <br> Recognizer Motoruna İlet]
            
            SPEECH_SEND_ASR --> SPEECH_RECOGNIZER_ENGINE(SpeechRecognition / Google STT)
            
            SPEECH_RECOGNIZER_ENGINE --> SPEECH_PARSE_RES{"Motor Sonuç <br> Döndürdü mü?"}
            SPEECH_PARSE_RES -- Hayır / Gürültü --> SESSİZLIK
            SPEECH_PARSE_RES -- Evet --> SPEECH_EXTRACT_TEXT[Tanınan Metni Al]
            
            SPEECH_EXTRACT_TEXT --> SPEECH_SET_LAST_SPEECH(SPEECH_last_speech_text <br>değişkenini güncelle)
            end
            
            SPEECH_SET_LAST_SPEECH --> SPEECH_AUTONOMY_PULL[Autonomy Modülü<br>Tarafından Poll Edilmeyi Bekle]
            SPEECH_AUTONOMY_PULL --> SESSİZLIK
        end
        subgraph SG_VLM_BRIDGE ["VLM_BRIDGE Modülü"]
            direction TB
            VLM_BRIDGE_START([Kamera / Remote Ingest]) --> VLM_BRIDGE_MODE{processing_mode}

            VLM_BRIDGE_MODE -- local --> VLM_BRIDGE_FACE_DET[Haar Face Detect]
            VLM_BRIDGE_FACE_DET --> VLM_BRIDGE_IDENT[ORB + FLANN ile yüz kimliği]
            VLM_BRIDGE_IDENT --> VLM_BRIDGE_RESULTS[latest_results güncelle]

            VLM_BRIDGE_RESULTS --> VLM_BRIDGE_FOLLOW{follow active}
            VLM_BRIDGE_FOLLOW -- Hayır --> VLM_BRIDGE_NORMAL[alerts + semantic + memory]
            VLM_BRIDGE_FOLLOW -- Evet --> VLM_BRIDGE_LOCK{CSRT kilidi var mı?}
            VLM_BRIDGE_LOCK -- Hayır --> VLM_BRIDGE_LOCK_FACE[Hedef yüz seç ve tracker kilitle]
            VLM_BRIDGE_LOCK -- Evet --> VLM_BRIDGE_UPDATE[CSRT bbox güncelle]
            VLM_BRIDGE_LOCK_FACE --> VLM_BRIDGE_TRACK
            VLM_BRIDGE_UPDATE --> VLM_BRIDGE_TRACK[Pan/Tilt hesapla ve /vlm/track gönder]

            VLM_BRIDGE_MODE -- remote --> VLM_BRIDGE_INGEST[POST /vlm/results]
            VLM_BRIDGE_INGEST --> VLM_BRIDGE_VALIDATE[Auth + normalize]
            VLM_BRIDGE_VALIDATE --> VLM_BRIDGE_REMOTE_RES[latest_results güncelle]
            VLM_BRIDGE_REMOTE_RES --> VLM_BRIDGE_REMOTE_FLOW{follow active}
            VLM_BRIDGE_REMOTE_FLOW -- Evet --> VLM_BRIDGE_SKIP[Remote action akışını bastır]
            VLM_BRIDGE_REMOTE_FLOW -- Hayır --> VLM_BRIDGE_NORMAL
        end
        subgraph SG_WAKEWORD ["WAKEWORD Modülü"]
            direction TB
            %% Ana Giriş
            WAKEWORD_START([Arka Plan Dinleme Thread'i]) --> WAKEWORD_SETUP_WW_ENGINE(Wakeword Motorunu Başlat <br> Porcupine / Snowboy)
            
            WAKEWORD_SETUP_WW_ENGINE --> WAKEWORD_WAIT_AUDIO[Mikrofondan Küçük<br>WAKEWORD_PCM Chunk'lar Oku]
            
            %% Arka Plan Döngüsü
            subgraph Background Listening [Srekli Dinleme ve Tetikleme]
            WAKEWORD_WAIT_AUDIO --> WAKEWORD_CHK_WAKEWORD{"Motor: 'Hey Sentry'<br>dedi mi?"}
            
            WAKEWORD_CHK_WAKEWORD -- Hayır --> WAKEWORD_DISCARD_CHUNK[Sesi Çöpe At] --> WAKEWORD_WAIT_AUDIO
            
            WAKEWORD_CHK_WAKEWORD -- Evet --> WAKEWORD_TRIGGER_ACT(Wakeword Algılandı <br> 'WAKEWORD__on_wakeword')
            end
            
            %% Tetikleme Sonrası İşlemler
            subgraph Trigger Actions [Tetikleme Aksiyonları]
            WAKEWORD_TRIGGER_ACT --> WAKEWORD_START_SPEECH_API(WAKEWORD_POST /speech/start <br> Konuşma Tanımayı Aç)
            WAKEWORD_START_SPEECH_API --> WAKEWORD_PUSH_EVENT(WAKEWORD_POST /interactions/event <br> 'wakeword.detected')
            
            WAKEWORD_PUSH_EVENT --> WAKEWORD_SOUND_CB{"Bip Sesi <br> Açıksa"}
            WAKEWORD_SOUND_CB -- Evet --> WAKEWORD_ARDU_BEEP(WAKEWORD_POST /arduino/send <br> buzzer bip)
            WAKEWORD_SOUND_CB -- Hayır --> WAKEWORD_START_WINDOW(Komut Dinleme Süresi Başlat)
            
            WAKEWORD_ARDU_BEEP --> WAKEWORD_START_WINDOW
            
            WAKEWORD_START_WINDOW --> WAKEWORD_TIMER_WAIT{"Bekle:<br>command_window_s <br>(Örn: 5 sn)"}
            
            WAKEWORD_TIMER_WAIT -- Süre Dolduğunda --> WAKEWORD_STOP_SPEECH_API(WAKEWORD_POST /speech/stop <br> Konuşma Tanımayı Kapat)
            end
            
            WAKEWORD_STOP_SPEECH_API --> WAKEWORD_WAIT_AUDIO
        end
    end
    subgraph LAYER_CORE ["2. MERKEZI KARAR VE YONETIM - BEYIN"]
        direction TB
        subgraph SG_AUTONOMY ["AUTONOMY Modülü"]
            direction TB
            %% Ana Döngü
            AUTONOMY_START_LOOP((Tick Döngüsü)) --> AUTONOMY_SENSE[AUTONOMY_SENSE: Algı Verilerini Topla]
            
            %% SENSE KISMI
            subgraph AUTONOMY_SENSE_PHASE ["Sense - Algılama"]
            AUTONOMY_S_SPEECH{"Yeni Konuşma<br>Var mı?"}
            AUTONOMY_S_DIR{"Ses Yönü<br> Değişti mi?"}
            AUTONOMY_S_VIS{"Görüntüde<br>Kişi Var mı?"}
            
            AUTONOMY_S_SPEECH -- Evet --> AUTONOMY_S_ADD_TXT(Konuşma Metnini Al)
            AUTONOMY_S_DIR -- Açı Değişimi > 10° --> AUTONOMY_S_TURN[O yöne kafayı çevir]
            AUTONOMY_S_VIS -- Evet --> AUTONOMY_S_MOOD_B[MoodManager'a<br>Mutluluk Puanı Ekle]
            end
            
            AUTONOMY_SENSE --> AUTONOMY_SENSE_PHASE
            AUTONOMY_SENSE_PHASE --> AUTONOMY_THINK[AUTONOMY_THINK: Düşün ve Karar Ver]
            
            %% THINK KISMI
            subgraph AUTONOMY_THINK_PHASE ["Think - Düşünme & Duygu Motoru"]
            AUTONOMY_T_TIME{"Uyku Saati mi?"}
            AUTONOMY_T_TIME -- Evet --> AUTONOMY_SLEEP_MODE[Düşük güç / Sakin nefes]
            AUTONOMY_T_TIME -- Hayır --> AUTONOMY_T_MOOD("mood.update Doğal Bozunma")
            
            AUTONOMY_T_MOOD --> AUTONOMY_T_SYNC[Baskın Duyguyu Seç<br>Örn: fear, joy, neutral]
            AUTONOMY_T_SYNC --> AUTONOMY_RANDOM_MICRO{Zar At: %40}
            AUTONOMY_RANDOM_MICRO -- Tutar --> AUTONOMY_DO_MICRO(Küçük Servo Titremesi<br>Canlılık Hissi)
            
            AUTONOMY_T_SYNC --> AUTONOMY_CHK_BORED{"Sıkılma Seviyesi<br>Yüksek mi?"}
            AUTONOMY_CHK_BORED -- Evet --> AUTONOMY_AGENTIC_CALL(AUTONOMY_LLM'e Karar Sor<br>Durum+Seçenekler)
            end
            
            AUTONOMY_THINK --> AUTONOMY_THINK_PHASE
            AUTONOMY_THINK_PHASE --> AUTONOMY_ACT[AUTONOMY_ACT: Konuşmaya Tepki Varsa]
            
            %% ACT KISMI (Konuşma Gelmişse)
            subgraph AUTONOMY_ACT_PHASE ["Act - Harekete Geçirme"]
            AUTONOMY_A_CHK_TXT{"Konuşma Metni<br>Dolu mu?"}
            AUTONOMY_A_CHK_TXT -- Hayır --> AUTONOMY_FINISH_LOOP((Tick Bitti))
            
            AUTONOMY_A_CHK_TXT -- Evet --> AUTONOMY_CHK_OWNER{"Sahip mi?"}
            AUTONOMY_CHK_OWNER -- Hayır / Kilitli --> AUTONOMY_REJECT[Erişim Reddedildi İşlemi] --> AUTONOMY_FINISH_LOOP
            
            AUTONOMY_CHK_OWNER -- Evet / Pas Geçildi --> AUTONOMY_USE_OLLAMA(Ollama Chat AUTONOMY_API Çağır)
            AUTONOMY_USE_OLLAMA --> AUTONOMY_RES_LLM(AUTONOMY_LLM Yanıtı: Text + Actions)
            
            AUTONOMY_RES_LLM --> AUTONOMY_PARSE_TAGS(AUTONOMY__apply_tags)
            
            AUTONOMY_PARSE_TAGS --> AUTONOMY_DO_OP[Donanım AUTONOMY_HTTP Çağrıları:<br>NeoPixel, AUTONOMY_TTS, Servo vb.] --> AUTONOMY_FINISH_LOOP
            end
            
            AUTONOMY_ACT --> AUTONOMY_ACT_PHASE
            AUTONOMY_FINISH_LOOP -->|time.sleep| AUTONOMY_START_LOOP
        end
        subgraph SG_CONFIG_CENTER ["CONFIG_CENTER Modülü"]
            direction TB
            %% Okuma Akışı
            CONFIG_CENTER_REQ_GET("GET /config") --> CONFIG_CENTER_READ_DISK("config.yml Oku")
            CONFIG_CENTER_READ_DISK --> CONFIG_CENTER_VALID_YAML{"YAML Geçerli mi?"}
            CONFIG_CENTER_VALID_YAML -- "Hayır" --> CONFIG_CENTER_LOAD_BACKUP("Backup Yükle")
            CONFIG_CENTER_VALID_YAML -- "Evet" --> CONFIG_CENTER_RET_CFG("JSON Olarak<br>Arayüze Dön")
            CONFIG_CENTER_LOAD_BACKUP --> CONFIG_CENTER_RET_CFG
            
            %% Yazma Akışı
            CONFIG_CENTER_REQ_POST("POST /config") --> CONFIG_CENTER_PARSE_NEW("Gelen JSON'ı Parse Et")
            CONFIG_CENTER_PARSE_NEW --> CONFIG_CENTER_VALID_SCHEMA{"Pydantic Şema<br>Doğrulaması?"}
            
            CONFIG_CENTER_VALID_SCHEMA -- "Hata" --> CONFIG_CENTER_RET_ERR("Hata Döndür:<br>Geçersiz Format")
            CONFIG_CENTER_VALID_SCHEMA -- "Başarılı" --> CONFIG_CENTER_SAVE_YAML("config.yml'e Yaz")
            
            CONFIG_CENTER_SAVE_YAML --> CONFIG_CENTER_RESTART_REQ{"Restart<br>Gerekiyor mu?"}
            CONFIG_CENTER_RESTART_REQ -- "Evet" --> CONFIG_CENTER_TRIG_RST("Modülü/Sistemi<br>Yeniden Başlat")
            CONFIG_CENTER_RESTART_REQ -- "Hayır" --> CONFIG_CENTER_HOT_RELOAD("Hafızadaki Objeyi<br>Güncelle (Hot-Reload)")
            
            CONFIG_CENTER_TRIG_RST --> CONFIG_CENTER_RET_OK("Başarılı")
            CONFIG_CENTER_HOT_RELOAD --> CONFIG_CENTER_RET_OK
        end
        subgraph SG_GATEWAY ["GATEWAY Modülü"]
            direction TB
            %% Başlangıç
            GATEWAY_START([GATEWAY_run_robot.py]) --> GATEWAY_INIT_LOG["init_logging_<br> Hata Yoksayılır"]
            GATEWAY_INIT_LOG --> GATEWAY_LOAD_CFG["load_config: <br> config.yml okuma"]
            GATEWAY_LOAD_CFG --> GATEWAY_CREATE_APP[GATEWAY_create_app]
            
            %% create_app iç akışı
            subgraph GATEWAY_create_app ["FastAPI Oluşturma"]
            GATEWAY_APP_INIT[FastAPI Uygulaması Başlat] --> GATEWAY_STATE_INIT[app.state.started empty]
            GATEWAY_STATE_INIT --> GATEWAY_CALL_BOOTSTRAP[bootstrap app, cfg]
            GATEWAY_CALL_BOOTSTRAP --> GATEWAY_CORE_API[Core GATEWAY_API /status mount]
            end
            
            GATEWAY_CREATE_APP --> GATEWAY_APP_INIT
            
            %% Bootstrap Akışı
            subgraph GATEWAY_Bootstrap ["Modül Yükleme Karar Ağacı"]
            GATEWAY_B_START([bootstrap başlar]) --> GATEWAY_READ_INC{"cfg.include var mı?"}
            GATEWAY_READ_INC -- Hayır --> GATEWAY_B_END([Döndür: started list])
            GATEWAY_READ_INC -- Evet --> GATEWAY_CHK_ARDUINO{"include.arduino == true?"}
            
            %% Arduino
            GATEWAY_CHK_ARDUINO -- Evet --> GATEWAY_TRY_ARD[arduino.GATEWAY__include_arduino]
            GATEWAY_TRY_ARD --> GATEWAY_CATCH_ARD{"Hata var mı?"}
            GATEWAY_CATCH_ARD -- Evet --> GATEWAY_LOG_ARD[warning: module failed] --> GATEWAY_CHK_VIS
            GATEWAY_CATCH_ARD -- Hayır --> GATEWAY_ADD_ARD[started arduino True] --> GATEWAY_CHK_VIS
            GATEWAY_CHK_ARDUINO -- Hayır --> GATEWAY_CHK_VIS{"include.vlm_bridge == true?"}
            
            %% VLM Bridge
            GATEWAY_CHK_VIS -- Evet --> GATEWAY_TRY_VIS[vlm.GATEWAY__include_vlm_bridge]
            GATEWAY_TRY_VIS --> GATEWAY_CATCH_VIS{"Hata var mı?"}
            GATEWAY_CATCH_VIS -- Evet --> GATEWAY_LOG_VIS[warning: module failed] --> GATEWAY_CHK_AUTO
            GATEWAY_CATCH_VIS -- Hayır --> GATEWAY_ADD_VIS[started GATEWAY_vlm_bridge True] --> GATEWAY_CHK_AUTO
            GATEWAY_CHK_VIS -- Hayır --> GATEWAY_CHK_AUTO{"include.autonomy == true?"}
            
            %% Autonomy (Diğerleri benzer mantıkta olduğu için temsilidir)
            GATEWAY_CHK_AUTO -- Evet --> GATEWAY_TRY_AUTO[autonomy.GATEWAY__include_autonomy]
            GATEWAY_TRY_AUTO --> GATEWAY_CATCH_AUTO{"Hata var mı?"}
            GATEWAY_CATCH_AUTO -- Evet --> GATEWAY_LOG_AUTO[warning: module failed] --> GATEWAY_CHK_OTHER
            GATEWAY_CATCH_AUTO -- Hayır --> GATEWAY_ADD_AUTO[started autonomy ServiceClient] --> GATEWAY_CHK_OTHER
            GATEWAY_CHK_AUTO -- Hayır --> GATEWAY_CHK_OTHER{"Diğer 20+ Modül <br> neopixel, speak, vb."}
            
            %% Diğerleri
            GATEWAY_CHK_OTHER --> GATEWAY_B_END
            end
            
            GATEWAY_CALL_BOOTSTRAP --> GATEWAY_B_START
            GATEWAY_B_END --> GATEWAY_CORE_API
            GATEWAY_CORE_API --> GATEWAY_RUN_UVICORN([uvicorn.run host:port])
        end
        subgraph SG_INTERACTIONS ["INTERACTIONS Modülü"]
            direction TB
            INTERACTIONS_START((Tick Timer <br> Her 1 saniye)) --> INTERACTIONS_GATHER_METRICS
            
            %% Metrik Toplama
            subgraph INTERACTIONS_SENSE_METRICS ["Metrik Toplama MetricsCollector"]
            INTERACTIONS_GATHER_METRICS[Sistem Verilerini Oku] --> INTERACTIONS_CPU_T(INTERACTIONS_CPU Sıcaklık)
            INTERACTIONS_GATHER_METRICS --> INTERACTIONS_CPU_L(INTERACTIONS_CPU Yük %si)
            INTERACTIONS_GATHER_METRICS --> INTERACTIONS_NET_T(Ağ Trafiği / Burst)
            INTERACTIONS_GATHER_METRICS --> INTERACTIONS_ARDU_C{Arduino <br>Heartbeat<br>Aktif mi?}
            
            INTERACTIONS_ARDU_C -- Evet --> INTERACTIONS_ARDU_OK[Arduino Alive]
            INTERACTIONS_ARDU_C -- Hayır --> INTERACTIONS_ARDU_ERR[Arduino Dead]
            
            INTERACTIONS_CPU_T --> INTERACTIONS_MERGE_M
            INTERACTIONS_CPU_L --> INTERACTIONS_MERGE_M
            INTERACTIONS_NET_T --> INTERACTIONS_MERGE_M
            INTERACTIONS_ARDU_OK --> INTERACTIONS_MERGE_M
            INTERACTIONS_ARDU_ERR --> INTERACTIONS_MERGE_M
            INTERACTIONS_MERGE_M[Tam Metrik Sözlüğü]
            end
            
            INTERACTIONS_MERGE_M --> INTERACTIONS_READ_EVENTS
            
            %% Olay Toplama
            subgraph INTERACTIONS_READ_EVENTS_Q ["Olay Kuyruğunu Oku"]
            INTERACTIONS_READ_EVENTS[INTERACTIONS_API /event Kuyruğunu Çek] --> INTERACTIONS_HAS_EVT{Kuyrukta Olay<br>Var mı?}
            INTERACTIONS_HAS_EVT -- Evet --> INTERACTIONS_POP_EVT(Olayları Metrik <br> Sözlüğüne Ekle)
            INTERACTIONS_HAS_EVT -- Hayır --> INTERACTIONS_KEEP_VAR(Sadece Metrikler)
            INTERACTIONS_POP_EVT --> INTERACTIONS_CONTEXT_DICT
            INTERACTIONS_KEEP_VAR --> INTERACTIONS_CONTEXT_DICT
            end
            
            INTERACTIONS_CONTEXT_DICT --> INTERACTIONS_EVAL_RULES
            
            %% Kural Değerlendirme Döngüsü
            subgraph INTERACTIONS_RULE_EVALUATION ["Kural Değerlendirme Motoru"]
            INTERACTIONS_EVAL_RULES[Tüm Kuralları Sırayla Kontrol Et]
            
            INTERACTIONS_EVAL_RULES --> INTERACTIONS_RULE_1{Kural 1: <br> if arduino == dead?}
            INTERACTIONS_RULE_1 -- Evet (Öncelik 100) --> INTERACTIONS_ACT_ERR[Kırmızı Renk, <br> breathe Animasyonu]
            
            INTERACTIONS_RULE_1 -- Hayır --> INTERACTIONS_RULE_2{Kural 2: <br> if INTERACTIONS_cpu_temp > 85?}
            INTERACTIONS_RULE_2 -- Evet (Öncelik 90) --> INTERACTIONS_ACT_HOT[Turuncu Renk, <br> pulse Animasyonu]
            
            INTERACTIONS_RULE_2 -- Hayır --> INTERACTIONS_RULE_3{Kural 3: <br> if event == autonomy.greet?}
            INTERACTIONS_RULE_3 -- Evet (Öncelik 80) --> INTERACTIONS_ACT_GREET[Yeşil Renk, <br> wave Animasyonu]
            
            INTERACTIONS_RULE_3 -- Hayır --> INTERACTIONS_RULE_N{Kural N...}
            INTERACTIONS_RULE_N -- Hiçbiri Uymadıysa --> INTERACTIONS_ACT_DEF[Varsayılan Taban Animasyonu: INTERACTIONS_BREATHE]
            
            INTERACTIONS_ACT_ERR --> INTERACTIONS_SEND_NEO
            INTERACTIONS_ACT_HOT --> INTERACTIONS_SEND_NEO
            INTERACTIONS_ACT_GREET --> INTERACTIONS_SEND_NEO
            INTERACTIONS_ACT_DEF --> INTERACTIONS_SEND_NEO
            end
            
            INTERACTIONS_SEND_NEO(NeoHttpClient) --> INTERACTIONS_HTTP_REQ([INTERACTIONS_HTTP INTERACTIONS_POST /neopixel/animate])
        end
        subgraph SG_STATE_MANAGER ["STATE_MANAGER Modülü"]
            direction TB
            %% Veri Yazma (SET)
            subgraph Update Flow [Durum Güncelleme İşlemi STATE_MANAGER_POST]
            STATE_MANAGER_REQ_UPDATE([STATE_MANAGER_POST /set/emotions <br> veya /set/battery]) --> STATE_MANAGER_PARSE_PAYLOAD(STATE_MANAGER_JSON Body Al)
            
            STATE_MANAGER_PARSE_PAYLOAD --> STATE_MANAGER_VALIDATE_PAYLOAD{"Anahtarlar <br> Geçerli mi?"}
            
            STATE_MANAGER_VALIDATE_PAYLOAD -- Hayır --> STATE_MANAGER_RET_ERR_U([Hata Döndür])
            STATE_MANAGER_VALIDATE_PAYLOAD -- Evet --> STATE_MANAGER_MUTEX_LOCK(Kilit Al - Thread Safe)
            
            STATE_MANAGER_MUTEX_LOCK --> STATE_MANAGER_MERGE_DICT[Store İçindeki Dictionary'e <br> Yeni Veriyi Merge Et] --> STATE_MANAGER_MUTEX_REL(Kilidi Bırak)
            
            STATE_MANAGER_MUTEX_REL --> STATE_MANAGER_TRIG_PUB_SUB{"Değişim Bildirimi <br> Aboneleri Var mı?"}
            STATE_MANAGER_TRIG_PUB_SUB -- Evet --> STATE_MANAGER_NOTIFY_SUBS(Abonelere Event Pushing) --> STATE_MANAGER_RET_OK_U([Başarılı])
            STATE_MANAGER_TRIG_PUB_SUB -- Hayır --> STATE_MANAGER_RET_OK_U
            end
            
            %% Veri Okuma (GET)
            subgraph Read Flow [Durum Okuma İşlemi STATE_MANAGER_GET]
            STATE_MANAGER_REQ_READ([STATE_MANAGER_GET /get/emotions <br> veya /state]) --> STATE_MANAGER_PARSE_QRY(Query Parametresi Al <br> Varsa Sadece Onu Ver)
            
            STATE_MANAGER_PARSE_QRY --> STATE_MANAGER_GET_LOCK[Kilit Al] --> STATE_MANAGER_CLONE_DAT[Kopya Oluştur <br> copy.deepcopy] --> STATE_MANAGER_UNLOCK[Kilidi Bırak]
            
            STATE_MANAGER_UNLOCK --> STATE_MANAGER_RET_JSON([Seçili State STATE_MANAGER_JSON'ı Dön])
            end
        end
    end
    subgraph LAYER_AI ["3. YAPAY ZEKA VE RAG"]
        direction TB
        subgraph SG_OLLAMA ["OLLAMA Modülü"]
            direction TB
            %% Ana Çağrı
            OLLAMA_API_IN([OLLAMA_POST /chat]) --> OLLAMA_CHAT_MET[OllamaChatService.chat text, OLLAMA_apply_actions]
            
            OLLAMA_CHAT_MET --> OLLAMA_GET_PERSONA[PersonaProvider.OLLAMA_system_prompt name]
            OLLAMA_GET_PERSONA --> OLLAMA_CHK_PERSONA{Kişilik var mı?}
            
            OLLAMA_CHK_PERSONA -- Hayır --> OLLAMA_DEF_PERSONA[Varsayılan sentry seç]
            OLLAMA_CHK_PERSONA -- Evet --> OLLAMA_USE_PERSONA[Kişilik sistem metni al]
            
            OLLAMA_USE_PERSONA --> OLLAMA_GET_HIST[ChatMemory.OLLAMA_get_context]
            OLLAMA_DEF_PERSONA --> OLLAMA_GET_HIST
            
            OLLAMA_GET_HIST --> OLLAMA_BLD_PROMPT{Mesajları Birleştir <br> System + History + User}
            
            OLLAMA_BLD_PROMPT --> OLLAMA_OLLAMA_API(OllamaClient.OLLAMA_generate_json)
            
            %% Ollama API Yanıt Döngüsü
            subgraph OLLAMA_Ollama_API ["LLM İstek İşlemi"]
            OLLAMA_REQ[LLMe OLLAMA_HTTP OLLAMA_POST <br> format: json] --> OLLAMA_RESP{OLLAMA_HTTP 200 mü?}
            OLLAMA_RESP -- Hayır --> OLLAMA_ERR_RET([error: Failed to reach OLLAMA_LLM])
            OLLAMA_RESP -- Evet --> OLLAMA_RAW_JSON(Yanıt Metni Al)
            end
            
            OLLAMA_OLLAMA_API --> OLLAMA_REQ
            OLLAMA_RAW_JSON --> OLLAMA_PARSE_JSON_P{Pydantic Modelle<br>OLLAMA_JSON Parse Et}
            
            %% JSON Ayrıştırma Mantığı
            subgraph OLLAMA_Parse_Logic ["Çıktı Ayrıştırma if/else"]
            OLLAMA_PARSE_JSON_P -- Başarılı (Valid OLLAMA_JSON) --> OLLAMA_P_SUCCESS[text, thoughts, actions<br>değişkenlerini ata]
            OLLAMA_PARSE_JSON_P -- Başarısız (Syntax Error) --> OLLAMA_EXTRACT_TAGS[OLLAMA_extract_llm_tags OLLAMA_raw_text <br> Regex ile OLLAMA_XML tagleri ara]
            
            OLLAMA_EXTRACT_TAGS --> OLLAMA_TAGS_RES[actions array oluştur]
            
            OLLAMA_P_SUCCESS --> OLLAMA_APPLY_ACT
            OLLAMA_TAGS_RES --> OLLAMA_APPLY_ACT
            end
            
            %% Etkileşim Kararı
            OLLAMA_APPLY_ACT{OLLAMA_apply_actions=True?}
            OLLAMA_APPLY_ACT -- Hayır --> OLLAMA_SAVE_MEM(ChatMemory.OLLAMA_add_interaction)
            OLLAMA_APPLY_ACT -- Evet --> OLLAMA_HTTP_POST_BRAIN(OLLAMA_POST /autonomy/OLLAMA_apply_actions)
            
            OLLAMA_SAVE_MEM --> OLLAMA_RET_FINAL([OLLAMA_API Yanıtı Döndür])
            OLLAMA_HTTP_POST_BRAIN --> OLLAMA_SAVE_MEM
        end
    end
    subgraph LAYER_ACT ["4. FIZIKSEL EYLEM VE TEPKI"]
        direction TB
        subgraph SG_ANIMATE ["ANIMATE Modülü"]
            direction TB
            %% Ana Giriş
            ANIMATE_API_REQ([ANIMATE_POST /animate/run]) --> ANIMATE_PARSE_REQ(Parametreler: <br> name, speed, loop)
            
            ANIMATE_PARSE_REQ --> ANIMATE_CHK_NAME{"Animasyon<br>adı geçerli mi?"}
            
            %% Dosya Yükleme Kararları
            subgraph Loading Logic [ANIMATE_YAML Yükleme ve Doğrulama]
            ANIMATE_CHK_NAME -- Hayır --> ANIMATE_RET_ERR([Hata: name gerekli])
            ANIMATE_CHK_NAME -- Evet --> ANIMATE_CHK_YAML(Dosyayı Oku: <br> animations/name.yml)
            
            ANIMATE_CHK_YAML --> ANIMATE_IS_EXIST{"Dosya Var mı?"}
            ANIMATE_IS_EXIST -- Hayır --> ANIMATE_RET_NF([Hata: Animasyon Bulunamadı])
            
            ANIMATE_IS_EXIST -- Evet --> ANIMATE_PARSE_YAML{"YAML formatı<br>doğru mu? (steps listesi)"}
            ANIMATE_PARSE_YAML -- Hayır --> ANIMATE_RET_INV([Hata: Geçersiz Format])
            end
            
            %% Oynatma Motoru (Sequencer)
            subgraph Engine Loop [Oynatma Motoru / Sequencer Döngüsü]
            ANIMATE_PARSE_YAML -- Evet --> ANIMATE_EXTRACT_STEPS(Tüm 'steps' listesini al)
            
            ANIMATE_EXTRACT_STEPS --> ANIMATE_LOOP_STEP[Döngü: Her step için]
            ANIMATE_LOOP_STEP --> ANIMATE_CALC_DUR(Hesapla: <br> duration = step.ANIMATE_duration_ms / speed)
            
            ANIMATE_CALC_DUR --> ANIMATE_CHK_POSE{"Pose Verisi <br> Var mı?"}
            
            ANIMATE_CHK_POSE -- Evet --> ANIMATE_ACT_SRV(Arduino Serial:<br> 'ANIMATE_set_pose' komutu gönder) --> ANIMATE_ACT_WAIT(Bekle: 1 veya hesaplanan <br> süre kadar delay)
            ANIMATE_CHK_POSE -- Hayır --> ANIMATE_ACT_WAIT
            
            ANIMATE_ACT_WAIT --> ANIMATE_NEXT_STEP{"Bitti mi?"}
            ANIMATE_NEXT_STEP -- Hayır --> ANIMATE_LOOP_STEP
            end
            
            ANIMATE_NEXT_STEP -- Evet --> ANIMATE_CHK_LOOP{"Loop = True mu?"}
            ANIMATE_CHK_LOOP -- Evet --> ANIMATE_EXTRACT_STEPS
            ANIMATE_CHK_LOOP -- Hayır --> ANIMATE_RET_OK([ok: true])
        end
        subgraph SG_ARDUINO_SERIAL ["ARDUINO_SERIAL Modülü"]
            direction TB
            %% Başlatma Mantığı
            ARDUINO_SERIAL_START([start]) --> ARDUINO_SERIAL_CHK_THREAD{"Okuma Thread'i <br> çalışıyor mu?"}
            ARDUINO_SERIAL_CHK_THREAD -- Evet --> ARDUINO_SERIAL_IGNORE([Hiçbir Şey Yapma])
            ARDUINO_SERIAL_CHK_THREAD -- Hayır --> ARDUINO_SERIAL_FIND_PORT(Seri Portu Bul <br> ARDUINO_SERIAL__autodetect_port)
            
            ARDUINO_SERIAL_FIND_PORT --> ARDUINO_SERIAL_CHK_PORT{"Port Bulundu mu?"}
            ARDUINO_SERIAL_CHK_PORT -- Hayır --> ARDUINO_SERIAL_ERR_START([ARDUINO_SERIAL_HATA: Port Yok veya Erişilemez])
            ARDUINO_SERIAL_CHK_PORT -- Evet --> ARDUINO_SERIAL_OPEN_SERIAL(SerialTransport Başlat)
            
            ARDUINO_SERIAL_OPEN_SERIAL --> ARDUINO_SERIAL_CREATE_THREADS(Send ve Read <br> Queue Oluştur)
            ARDUINO_SERIAL_CREATE_THREADS --> ARDUINO_SERIAL_RUN_THREAD[Arka Plan ARDUINO_SERIAL__read_loop Oku]
            
            %% Arka Plan Okuma Döngüsü (Read Loop)
            subgraph ARDUINO_SERIAL_ReadLoop ["Arka Plan Okuma Akışı"]
            ARDUINO_SERIAL_LOOP_START((Döngü Başı)) --> ARDUINO_SERIAL_READ_LINE{"Seri Porttan<br>Satır Oku"}
            ARDUINO_SERIAL_READ_LINE -- Boş / Timeout --> ARDUINO_SERIAL_LOOP_START
            ARDUINO_SERIAL_READ_LINE -- Veri Var --> ARDUINO_SERIAL_PARSE_JSON{"JSON Parse <br> Başarılı mı?"}
            ARDUINO_SERIAL_PARSE_JSON -- Hayır --> ARDUINO_SERIAL_LOG_ERR[Hata Logla] --> ARDUINO_SERIAL_LOOP_START
            ARDUINO_SERIAL_PARSE_JSON -- Evet --> ARDUINO_SERIAL_INGEST(ARDUINO_SERIAL_JSON Verisini İşle <br> ARDUINO_SERIAL__ingest_message)
            
            ARDUINO_SERIAL_INGEST --> ARDUINO_SERIAL_CHK_TYPE{Gelen Mesaj Türü}
            
            ARDUINO_SERIAL_CHK_TYPE -- ARDUINO_SERIAL_RFID Olayı --> ARDUINO_SERIAL_EVENT_RFID[ARDUINO_SERIAL_RFID Handler <br> ARDUINO_SERIAL__record_rfid / Webhook] --> ARDUINO_SERIAL_LOOP_START
            ARDUINO_SERIAL_CHK_TYPE -- Telemetri --> ARDUINO_SERIAL_EVENT_TLM[Telemetri Handler <br> Global Durum] --> ARDUINO_SERIAL_LOOP_START
            ARDUINO_SERIAL_CHK_TYPE -- Yanıt (ok / error) --> ARDUINO_SERIAL_QUEUE_PUSH[Uygulama Yanıt<br>Kuyruğuna Koy] --> ARDUINO_SERIAL_LOOP_START
            end
            
            ARDUINO_SERIAL_RUN_THREAD --> ARDUINO_SERIAL_LOOP_START
            
            %% Komut Gönderme Akışı
            subgraph ARDUINO_SERIAL_WriteCycle ["Komut Gönderme - send/request"]
            ARDUINO_SERIAL_API_CALL([ARDUINO_SERIAL_request_cmd]) --> ARDUINO_SERIAL_MAKE_JSON(ARDUINO_SERIAL_JSON'a Çevir + <br> Satır Sonu Ekle)
            ARDUINO_SERIAL_MAKE_JSON --> ARDUINO_SERIAL_CHK_ALIVE{"Bağlantı Açık mı?"}
            ARDUINO_SERIAL_CHK_ALIVE -- Hayır --> ARDUINO_SERIAL_RET_NONE([None Döndür])
            ARDUINO_SERIAL_CHK_ALIVE -- Evet --> ARDUINO_SERIAL_WRITE(Serial Write)
            ARDUINO_SERIAL_WRITE --> ARDUINO_SERIAL_WAIT_Q{"Okuma Kuyruğunda<br>Yanıt Bekle - Timeout"}
            ARDUINO_SERIAL_WAIT_Q -- Timeout --> ARDUINO_SERIAL_RET_ERR([Hata Formatı Döndür])
            ARDUINO_SERIAL_WAIT_Q -- Yanıt Geldi --> ARDUINO_SERIAL_RET_RESP([Yanıtı Döndür])
            end
        end
        subgraph SG_NEOPIXEL ["NEOPIXEL Modülü"]
            direction TB
            %% Ana Giriş
            NEOPIXEL_API_REQ([NEOPIXEL_HTTP NEOPIXEL_POST /animate]) --> NEOPIXEL_PARSE_REQ(Gelen parametreler: <br> name, emotions, r, g, b, speed, loop)
            
            NEOPIXEL_PARSE_REQ --> NEOPIXEL_CHK_NAME{"Animasyon<br>Adı Var mı?"}
            
            %% Animasyon Yürütme Döngüsü
            subgraph Animation Pipeline [Animasyon Yürütme ve Renk Seçimi]
            
            NEOPIXEL_CHK_NAME -- Hayır --> NEOPIXEL_RET_ERR([Hata: name gerekli])
            NEOPIXEL_CHK_NAME -- Evet --> NEOPIXEL_CHK_COLOR{"r,g,b<br>verilmiş mi?"}
            
            %% Renk Belirleme Karar Ağacı
            NEOPIXEL_CHK_COLOR -- Evet --> NEOPIXEL_SET_RGB[r,g,b Kullan]
            NEOPIXEL_CHK_COLOR -- Hayır --> NEOPIXEL_CHK_EMOTION{"Emotions Listesi<br>Verilmiş mi?"}
            
            NEOPIXEL_CHK_EMOTION -- Evet --> NEOPIXEL_LOOP_EMO[Duyguları Sırayla Kontrol Et: <br> joy, curiosity...]
            NEOPIXEL_LOOP_EMO --> NEOPIXEL_FETCH_YML[EmotionStore'dan <br> emotion.yml Yükle]
            NEOPIXEL_FETCH_YML --> NEOPIXEL_CHK_YML{"Dosya ve Renk<br>Var mı?"}
            
            NEOPIXEL_CHK_YML -- Evet --> NEOPIXEL_RAND_PICK(Listeden Rastgele<br>Renk Seç) --> NEOPIXEL_SET_RGB
            NEOPIXEL_CHK_YML -- Hayır --> NEOPIXEL_LOOP_EMO
            
            NEOPIXEL_CHK_EMOTION -- Hayır --> NEOPIXEL_SET_DEF[Varsayılan: Beyaz <br> r=255, g=255, b=255] --> NEOPIXEL_SET_RGB
            
            %% Animasyon Tetikleme
            NEOPIXEL_SET_RGB --> NEOPIXEL_RUNNER_CALL(NeoRunner.animate)
            NEOPIXEL_RUNNER_CALL --> NEOPIXEL_DRIVER_CALL(NeoDriver.animate)
            
            %% Sürücü Karar Aşaması
            NEOPIXEL_DRIVER_CALL --> NEOPIXEL_CHK_HW{"Pi5Neo SPI<br>Erişilebilir mi?"}
            NEOPIXEL_CHK_HW -- Evet --> NEOPIXEL_HW_RUN(Donanım Hızlandırmalı<br>Sürücü - C modülü)
            NEOPIXEL_CHK_HW -- Hayır --> NEOPIXEL_SIM_RUN(NEOPIXEL__SimStrip - Geliştirici<br>Simülatörü Buffer'ı)
            end
            
            NEOPIXEL_HW_RUN --> NEOPIXEL_RET_OK([ok: true])
            NEOPIXEL_SIM_RUN --> NEOPIXEL_RET_OK
        end
        subgraph SG_PISERVO ["PISERVO Modülü"]
            direction TB
            %% PiServo Akışı
            PISERVO_REQ_SRV("POST /piservo/set") --> PISERVO_PARSE_ID("Hangi Kulak?<br>Sol (12) / Sağ (13)")
            
            PISERVO_PARSE_ID --> PISERVO_CHK_LIB{"RPi.GPIO<br>Kurulu mu?"}
            
            PISERVO_CHK_LIB -- "Hayır (PC/Mac)" --> PISERVO_LOG_MOCK("Uyarı: RPi.GPIO Yok<br>Yazılımsal Simülasyon (Mock)")
            PISERVO_CHK_LIB -- "Evet" --> PISERVO_SET_DUTY("Açı (0-180) -> Duty Cycle (%)<br>Dönüştür")
            
            PISERVO_SET_DUTY --> PISERVO_APLY_PWM("pwm.ChangeDutyCycle(val)")
            PISERVO_LOG_MOCK --> PISERVO_APLY_PWM
            
            PISERVO_APLY_PWM --> PISERVO_RET_OK("Başarılı")
        end
        subgraph SG_SPEAK ["SPEAK Modülü"]
            direction TB
            %% Ana Giriş
            SPEAK_API_REQ([SPEAK_POST /speak/say]) --> SPEAK_PARSE_REQ(Gelen parametreler: <br> text, tone, engine)
            
            SPEAK_PARSE_REQ --> SPEAK_CHK_TEXT{"Metin/Text <br> Boş mu?"}
            
            %% API Kontrolleri
            subgraph SPEAK_TTS Request Validation [İstek Doğrulama & Temizlik]
            SPEAK_CHK_TEXT -- Evet --> SPEAK_RET_ERR([Hata: Text Gerekli])
            SPEAK_CHK_TEXT -- Hayır --> SPEAK_CLEAN_TEXT(Regex ile Markdown <br> ve SPEAK_JSON Artıklarını Temizle)
            SPEAK_CLEAN_TEXT --> SPEAK_CHK_ENGINE{"Hangi Motor?"}
            end
            
            %% Motor Seçimi
            subgraph Engine Selection [SPEAK_TTS Motoru Seçimi]
            SPEAK_CHK_ENGINE -- Default / pyttsx3 --> SPEAK_ENGINE_PYTTS(pyttsx3)
            SPEAK_CHK_ENGINE -- Piper --> SPEAK_ENGINE_PIPER(Piper / Offline Türkçe)
            SPEAK_CHK_ENGINE -- Diğer (espeak, vb.) --> SPEAK_ENGINE_DEF(Fallback Engine)
            end
            
            SPEAK_ENGINE_PYTTS --> SPEAK_APPLY_TONE
            SPEAK_ENGINE_PIPER --> SPEAK_APPLY_TONE
            SPEAK_ENGINE_DEF --> SPEAK_APPLY_TONE
            
            %% Duygusal Tonlama ve Sentezleme
            subgraph Tone Application [Duygu / Ton Ayarlama]
            SPEAK_APPLY_TONE --> SPEAK_CHK_TONE{"Tone Değeri: <br> 'happy', 'sad', 'angry' ..."}
            
            SPEAK_CHK_TONE -- happy --> SPEAK_SET_H[Hız: +%20, Ses: +%10] --> SPEAK_SYNTHESIZE
            SPEAK_CHK_TONE -- sad --> SPEAK_SET_S[Hız: -%25, Ses: -%20] --> SPEAK_SYNTHESIZE
            SPEAK_CHK_TONE -- angry --> SPEAK_SET_A[Hız: +%10, Ses: SPEAK_MAX] --> SPEAK_SYNTHESIZE
            SPEAK_CHK_TONE -- neutral / Yok --> SPEAK_SET_N[Normal Hız ve Ses] --> SPEAK_SYNTHESIZE
            
            SPEAK_SYNTHESIZE(SPEAK_TTS Sentezleme ve <br> SPEAK_ALSA / aplay ile Oynatma)
            end
            
            SPEAK_SYNTHESIZE --> SPEAK_DONE([ok: true])
        end
    end
    subgraph LAYER_BG ["5. ARKA PLAN SERVISLERI"]
        direction TB
        subgraph SG_CALIBRATION ["CALIBRATION Modülü"]
            direction TB
            %% Kalibrasyon Modu Başlatma
            CALIBRATION_START(Kalibrasyon Modu İsteği) --> CALIBRATION_GET_REQ(CALIBRATION_POST /calibration/start)
            
            CALIBRATION_GET_REQ --> CALIBRATION_CHK_STATE{Robot Hareket<br>Halinde mi?}
            
            CALIBRATION_CHK_STATE -- Evet --> CALIBRATION_RET_BUSY(Hata: Önce robotu durdurun)
            CALIBRATION_CHK_STATE -- Hayır --> CALIBRATION_SET_STATE(Mod = CALIBRATION_CALIBRATION_MODE)
            
            %% Çekirdek Döngü
            subgraph Kalibrasyon Döngüsü
            CALIBRATION_SET_STATE --> CALIBRATION_RECV_CMD(İstemciden Servo Açısı Al Örn: pan: 95)
            CALIBRATION_RECV_CMD --> CALIBRATION_SEND_ARDU(Arduinoya Doğrudan İlet: CALIBRATION_set_servo id value)
            CALIBRATION_SEND_ARDU --> CALIBRATION_WAIT_USR{Kullanıcı Onayı?}
            
            CALIBRATION_WAIT_USR -- Hayır (Değiştir) --> CALIBRATION_RECV_CMD
            CALIBRATION_WAIT_USR -- Evet (Kaydet) --> CALIBRATION_SAVE_CONF
            end
            
            %% Kaydetme Döngüsü
            subgraph Kalıcı Hafıza
            CALIBRATION_SAVE_CONF(Yapılandırmayı Yaz) --> CALIBRATION_CHK_DEST{Hedef Neresi?}
            
            CALIBRATION_CHK_DEST -- CALIBRATION_EEPROM --> CALIBRATION_SEND_EEP(Arduino CALIBRATION_EEPROM<br>Write Komutu)
            CALIBRATION_CHK_DEST -- Raspberry Pi --> CALIBRATION_WRITE_JSON(config.yml / calib.json<br>Üzerine Yaz)
            end
            
            CALIBRATION_SEND_EEP --> CALIBRATION_RET_OK(Başarılı)
            CALIBRATION_WRITE_JSON --> CALIBRATION_RET_OK
        end
        subgraph SG_DIAGNOSTICS ["DIAGNOSTICS Modülü"]
            direction TB
            %% Test Akışı
            DIAGNOSTICS_START("self_test Başlar") --> DIAGNOSTICS_CHK_ARDU{"Arduino<br>Ping"}
            DIAGNOSTICS_CHK_ARDU -- "Timeout" --> DIAGNOSTICS_FAIL_ARDU("Hata:<br>Arduino Bağlantısı Koptu")
            DIAGNOSTICS_CHK_ARDU -- "OK" --> DIAGNOSTICS_CHK_CAM{"Kamera<br>Cevap"}
            
            DIAGNOSTICS_CHK_CAM -- "Hata" --> DIAGNOSTICS_FAIL_CAM("Uyarı:<br>Kamera Bulunamadı")
            DIAGNOSTICS_CHK_CAM -- "OK" --> DIAGNOSTICS_CHK_LLM{"Ollama<br>Servisi"}
            
            DIAGNOSTICS_CHK_LLM -- "Kapalı" --> DIAGNOSTICS_FAIL_LLM("Uyarı:<br>Ollama Yok, Offline Mod")
            DIAGNOSTICS_CHK_LLM -- "OK" --> DIAGNOSTICS_FINISH_TEST
            
            DIAGNOSTICS_FAIL_ARDU --> DIAGNOSTICS_AGGREGATE
            DIAGNOSTICS_FAIL_CAM --> DIAGNOSTICS_AGGREGATE
            DIAGNOSTICS_FAIL_LLM --> DIAGNOSTICS_AGGREGATE
            DIAGNOSTICS_FINISH_TEST --> DIAGNOSTICS_AGGREGATE
            
            DIAGNOSTICS_AGGREGATE("Tüm Test Sonuçlarını<br>JSON Olarak Topla") --> DIAGNOSTICS_CHK_CRIT{"Kritik Hata Var mı?"}
            
            DIAGNOSTICS_CHK_CRIT -- "Evet (Örn: Arduino)" --> DIAGNOSTICS_PLAY_ERR("Speak TTS ile 'Kritik sistem hatası' Sentezle<br>NeoPixel KIRMIZI")
            DIAGNOSTICS_CHK_CRIT -- "Hayır" --> DIAGNOSTICS_PLAY_OK("Tüm sistemler çevrimiçi<br>NeoPixel YEŞİL")
        end
        subgraph SG_LOGWRAPPER ["LOGWRAPPER Modülü"]
            direction TB
            %% Log Yakalama Akışı
            LOGWRAPPER_G_LOG("Herhangi Bir Modülde<br>logger.error/info") --> LOGWRAPPER_CATCH_HND("WebSocketLogHandler<br>Yakalar (Intercept)")
            
            LOGWRAPPER_CATCH_HND --> LOGWRAPPER_FMT_JSON("Zaman, Modül Adı, Renk<br>Bilgilerini JSON Yap")
            
            LOGWRAPPER_FMT_JSON --> LOGWRAPPER_WS_BCAST("Tüm Aktif WebSocket<br>İstemcilerine Yolla")
            
            %% WS İstekleri
            LOGWRAPPER_FRONTEND("Web Arayüzü<br>(Admin Panel)") --> LOGWRAPPER_REQ_WS("WS /logs/stream")
            LOGWRAPPER_REQ_WS --> LOGWRAPPER_ADD_CLIENT("İstemciyi Aktif Listeye<br>(clients_set) Ekle")
            LOGWRAPPER_ADD_CLIENT --> LOGWRAPPER_WAIT_LOGS("Log Bekleme Döngüsü")
            LOGWRAPPER_WS_BCAST --> LOGWRAPPER_WAIT_LOGS
        end
        subgraph SG_MUTAGEN ["MUTAGEN Modülü"]
            direction TB
            %% Sync Akışı
            MUTAGEN_START("Özel Geliştirici Scripti<br>(Örn: sync.bat)") --> MUTAGEN_CHK_MTG{"mutagen<br>kurulu mu?"}
            
            MUTAGEN_CHK_MTG -- "Hayır" --> MUTAGEN_ERR_MTG("Hata:<br>Mutagen CLI Bulunamadı")
            MUTAGEN_CHK_MTG -- "Evet" --> MUTAGEN_CREATE_SESSION("mutagen sync create<br>--name=sentrybot<br>./ -> pi@10.x.x.x:~/SentryBOT")
            
            MUTAGEN_CREATE_SESSION --> MUTAGEN_CHK_SESS{"Session Başarılı<br>Kuruldu mu?"}
            
            MUTAGEN_CHK_SESS -- "Hayır" --> MUTAGEN_ERR_SSH("Hata:<br>SSH Şifresi veya Host Yanlış")
            MUTAGEN_CHK_SESS -- "Evet" --> MUTAGEN_MON_SESS("mutagen sync monitor<br>sentrybot")
            
            %% Durum Yönetimi
            MUTAGEN_MON_SESS --> MUTAGEN_RUNNING("Sürekli Senkronizasyon<br>(İki yönlü + Ignore Listesi)")
        end
        subgraph SG_NOTIFIER ["NOTIFIER Modülü"]
            direction TB
            %% İstek Gelmesi
            NOTIFIER_EVT_TRIG("Herhangi Bir Modül:<br>POST /notify/send") --> NOTIFIER_PARSE_MSG("Parametre: title, message, level")
            
            NOTIFIER_PARSE_MSG --> NOTIFIER_CHK_LVL{"Level (Seviye)<br>Ne?"}
            
            NOTIFIER_CHK_LVL -- "INFO" --> NOTIFIER_SET_ICON("ℹ️ İkonu Ekle")
            NOTIFIER_CHK_LVL -- "WARNING" --> NOTIFIER_SET_ICON_W("⚠️ İkonu Ekle")
            NOTIFIER_CHK_LVL -- "CRITICAL" --> NOTIFIER_SET_ICON_C("🚨 İkonu Ekle")
            
            NOTIFIER_SET_ICON --> NOTIFIER_CHK_TEL{"Telegram Token<br>Tanımlı mı?"}
            NOTIFIER_SET_ICON_W --> NOTIFIER_CHK_TEL
            NOTIFIER_SET_ICON_C --> NOTIFIER_CHK_TEL
            
            %% API Gönderimi
            NOTIFIER_CHK_TEL -- "Evet" --> NOTIFIER_REQ_TEL("Telegram API'ye Req At<br>(SendMessage)")
            NOTIFIER_CHK_TEL -- "Hayır" --> NOTIFIER_CHK_DIS{"Discord Webhook<br>Var mı?"}
            
            NOTIFIER_REQ_TEL --> NOTIFIER_CHK_DIS
            
            NOTIFIER_CHK_DIS -- "Evet" --> NOTIFIER_REQ_DIS("Discord Webhook'a Req At")
            NOTIFIER_CHK_DIS -- "Hayır" --> NOTIFIER_FINISH_NOT("İşlem Bitti")
            NOTIFIER_REQ_DIS --> NOTIFIER_FINISH_NOT
        end
        subgraph SG_OTA ["OTA Modülü"]
            direction TB
            %% İstek Girişi
            OTA_START(OTA_POST /ota/update Dosya Icerir) --> OTA_CHK_ZIP{Zip/Tar<br>Geçerli mi?}
            
            %% Güvenlik ve Extract
            OTA_CHK_ZIP -- Hayır --> OTA_RET_ERR(Hata:<br>Dosya Bozuk veya Geçersiz)
            OTA_CHK_ZIP -- Evet --> OTA_EXTRACT_TMP(Geçici /tmp/OTA_sentry_upd<br>Klasörüne Aç)
            
            OTA_EXTRACT_TMP --> OTA_CHK_SIG{İmza/Checksum<br>Doğru mu?}
            OTA_CHK_SIG -- Hayır --> OTA_ABORT_UPD(Güvenlik İptali:<br>Geçersiz Paket)
            
            %% Kopyalama ve Yeniden Başlatma
            OTA_CHK_SIG -- Evet --> OTA_SHT_DOWN(Güvenli Mod<br>Tüm Motorları Sustur E Stop)
            
            OTA_SHT_DOWN --> OTA_CPY_FILES(Rsync veya Shutil ile<br>Kök Dizini Üzerine Yaz)
            
            OTA_CPY_FILES --> OTA_PIP_DEP{Yeni OTA_requirements_txt<br>var mı}
            OTA_PIP_DEP -- Evet --> OTA_RUN_PIP(Subprocess<br>pip install -r req txt)
            OTA_PIP_DEP -- Hayır --> OTA_TRIG_SYSTEMD(Systemd Servisini / PCyi<br>Yeniden Başlat Reboot)
            
            OTA_RUN_PIP --> OTA_TRIG_SYSTEMD
            OTA_TRIG_SYSTEMD --> OTA_EXIT_OK(Sistem Kapanıyor...)
        end
        subgraph SG_SCHEDULER ["SCHEDULER Modülü"]
            direction TB
            %% Zamanlayıcı Döngüsü
            SCHEDULER_START(Background Thread Her saniye uyanir) --> SCHEDULER_GET_TIME(Şu Anki Saati Al)
            
            SCHEDULER_GET_TIME --> SCHEDULER_CHK_CRON{Kayıtlı Görevlerin<br>Zamanı Geldi mi?}
            
            SCHEDULER_CHK_CRON -- Hayır --> SCHEDULER_SLEEP(sleep 1) --> SCHEDULER_START
            SCHEDULER_CHK_CRON -- Evet --> SCHEDULER_FORK_TASK(İlgili Fonksiyonu<br>Ayrı Threadde Başlat)
            
            %% Örnek Görevler
            SCHEDULER_FORK_TASK --> SCHEDULER_TASK_1(Gece 03:00<br>Sohbet Loglarını Temizle)
            SCHEDULER_FORK_TASK --> SCHEDULER_TASK_2(Sabah 08:00<br>Otonomi Uyanma Titremesi)
            SCHEDULER_FORK_TASK --> SCHEDULER_TASK_3(Her 30dk<br>Battery Metrik Logla)
            
            SCHEDULER_TASK_1 --> SCHEDULER_SLEEP
            SCHEDULER_TASK_2 --> SCHEDULER_SLEEP
            SCHEDULER_TASK_3 --> SCHEDULER_SLEEP
        end
        subgraph SG_TELEMETRY ["TELEMETRY Modülü"]
            direction TB
            %% Telemetri Kayıt Alma
            TELEMETRY_EVT_IN("Herhangi bir olay (Event)<br>(Örn: arduino.telemetry)") --> TELEMETRY_TELEM_RECORD("Değişkeni Hafızaya Kaydet")
            
            TELEMETRY_TELEM_RECORD --> TELEMETRY_CHK_KEY{"Gelen Veri<br>Tipi?"}
            
            TELEMETRY_CHK_KEY -- "Sensör Verisi" --> TELEMETRY_SET_SENS("telemetry['imu_pitch'] = 45")
            TELEMETRY_CHK_KEY -- "Robot Pozu" --> TELEMETRY_SET_POSE("telemetry['current_pose'] = 'stand'")
            TELEMETRY_CHK_KEY -- "Ping" --> TELEMETRY_SET_PING("Ping Gecikmesini (ms) Yaz")
            
            %% Prometheus Formatına Çevrilme
            TELEMETRY_HTTP_GET("GET /telemetry/metrics") --> TELEMETRY_LOOP_VARS("Tüm Hafızayı Gez")
            
            TELEMETRY_LOOP_VARS --> TELEMETRY_FMT_PROM("SentryBOT_metric type imu 45 SentryBOT_metric type ram 1024")
            
            TELEMETRY_FMT_PROM --> TELEMETRY_RET_TXT("Düz Metin (Plaintext)<br>Döndür")
        end
    end
    %% Katmanlar Arasi Yerlesim Zorlamasi
    LAYER_SENSE ~~~ LAYER_CORE
    LAYER_CORE ~~~ LAYER_AI
    LAYER_AI ~~~ LAYER_ACT
    LAYER_ACT ~~~ LAYER_BG
    %% GERCEK VERI AKISLARI
    SG_GATEWAY --> SG_AUTONOMY
    SG_GATEWAY --> SG_ARDUINO_SERIAL
    SG_GATEWAY --> SG_CAMERA
    WAKEWORD_WAIT_AUDIO -- "Tetik" --> SPEECH_START
    SPEECH_EXTRACT_TEXT -- "Metin" --> AUTONOMY_S_ADD_TXT
    CAMERA_SIGNAL_EVENT --> VLM_BRIDGE_START
    VLM_BRIDGE_IDENT -- "Kişi Algılandı" --> AUTONOMY_S_MOOD_B
    AUTONOMY_A_CHK_TXT -- "Soru" --> OLLAMA_API_IN
    OLLAMA_P_SUCCESS --> AUTONOMY_DO_OP
    AUTONOMY_DO_OP -- "/speak/say" --> SPEAK_API_REQ
    AUTONOMY_DO_OP -- "/neopixel" --> NEOPIXEL_API_REQ
    AUTONOMY_DO_OP -- "/animate" --> ANIMATE_API_REQ
    ANIMATE_ACT_SRV -- "Serial Req" --> ARDUINO_SERIAL_API_CALL
    CALIBRATION_SEND_ARDU --> ARDUINO_SERIAL_API_CALL
    INTERACTIONS_HTTP_REQ --> NEOPIXEL_API_REQ
```

## 🔄 Yaşam Döngüsünde Kritik Dönüm (Karar) Noktaları (Global Decisions)

Bu diyagramlar detayları kendi dosyalarında saklasa da, sistem geneli kararları burada özetleyebiliriz:

### 1. Kim Konuşuyor? (Access Control)
VLM'den gelen isim ve Arduino'dan okunan `g_lastOwnerUid` devamlı kontrol edilir.
- **İf:** Sesli bir soru geldi (`"Ne düşünüyorsun?"`) ve Owner kilidi açık (`require_owner: true`);
  - Robot soran yüze (Vision) veya RFID sensörüne bakar.
  - Eğer sahip yakında değilse soruyu Ollama LLM'e göndermeyi reddeder. Kırmızı gözlerle uyarı çalar.
  - Sahipse LLM'e gönderir.

### 2. Yapılandırılmış LLM mi Yoksa Regex mi?
Ollama 8B / LLaMA tarzı modeller her daim `{"text": "", "actions":[]}` düzgün JSON şeması veremezler (Syntax error atarlar).
- **Trz / Catch:** Ollama, API'dan string okur, `json.loads` dener. Eğer patlarsa Modül kendini kilitlemez. Autonomy `extract_llm_tags` (Regex Parser) devreye girer; textin içerisindeki `<speak>merhaba</speak>` gibi kalıntıları regex ile arayıp, zoraki JSON actions dictionary'sine kendisi paketler ve beyne sunar. Böylece robot çökmez.

### 3. CPU'yu Koruma Mekanizmaları (Throttling)
Raspberry Pi 5 cihazında ısı ve yük problemlerini kısmak için if blokları kurulmuştur.
- **VLM:** OpenCV tabanlı yüz algılama/takip döngüsü, hedef FPS sınırları ve tracker kayıp eşiği ile gereksiz CPU yükünü bastırır.
- **Wakeword:** Mikrofon sürekli dinler ancak STT/ASR (Whisper vb) kapalıdır. **Sadece** "Hey Sentry" wakeword tespit eden küçük işlem (Porcupine) tetiklendiğinde ASR 5 saniyeliğine çalıştırılır. Enerji tasarrufu en üst seviyeye çıkarılır.

## Sonuç

SentryBOT devasa özelliklerini, Gateway'in modüler bağımsız mimarisiyle ayakta tutar. Bir modülün API (HTTP) servisi çökse dahi, Autonomy `ServiceClient` üzerindeki 1 saniyelik API Timeout'lar sağolsun diğer özellikleri çalışmaya, robot "hayatta" kalmaya devam eder. Her bir modül bağımsız çalışacak mantığa (Microservice Pattern) oturtulmuştur.
