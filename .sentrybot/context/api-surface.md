# SentryBOT — API Yüzey Haritası (API Surface)

> Tüm modüllerin HTTP endpoint'leri bu dosyada listelenmiştir. AI asistanlar yeni endpoint eklerken veya modüller arası iletişim kurarken bu dosyayı referans alır.

## Gateway (Port 8080)

Tüm modüller Gateway üzerinden `/` kökünde mount olur. Her modülün endpoint'leri kendi prefix'i altındadır.

### Core Gateway Endpoints
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/status` | GET | Gateway ve tüm modüllerin durumu |
| `/health` | GET | Sağlık kontrolü |
| `/healthz` | GET | Kubernetes-style health check |

---

### Arduino Serial — `/arduino/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/arduino/send` | POST | Fire-and-forget komut gönder |
| `/arduino/request` | POST | ACK bekleyerek komut gönder (kritik komutlar için) |
| `/arduino/status` | GET | Bağlantı durumu |
| `/arduino/telemetry` | GET | Son telemetri verileri |

### Autonomy — `/autonomy/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/autonomy/apply_actions` | POST | LLM action'larını donanıma uygula |
| `/autonomy/status` | GET | Brain döngüsü durumu |
| `/autonomy/mood` | GET | Anlık duygu durumu |

### Agent Core — `/agent/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/agent/step` | POST | Tek agent adımı (tool loop) |
| `/agent/step_stream` | POST | SSE canlı durum + final cevap |
| `/agent/route_preview` | POST | Router seçim önizleme |
| `/agent/world_state` | GET | Dünya durumu (pil, sensörler) |
| `/agent/memory/search` | GET | Epizodik hafıza arama |
| `/agent/slam/location` | GET | Topolojik konum |
| `/agent/slam/pathfind` | GET | BFS yol bulma |
| `/agent/healthz` | GET | Agent durumu (BUSY/IDLE) |

### Camera — `/camera/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/camera/stream` | GET | MJPEG canlı stream |
| `/camera/snapshot` | GET | Tek kare yakala |
| `/camera/video` | GET | Video feed URL |

### VLM Bridge — `/vlm/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/vlm/results` | GET/POST | Algılama sonuçları (local/remote) |
| `/vlm/track` | POST | Pan/tilt takip komutu |
| `/vlm/follow/start` | POST | Yüz takibini başlat |
| `/vlm/follow/stop` | POST | Yüz takibini durdur |
| `/vlm/ask` | POST | VLM'e soru sor (sahne analizi) |

### Speech — `/speech/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/speech/start` | POST | ASR dinlemeyi başlat |
| `/speech/stop` | POST | ASR dinlemeyi durdur |
| `/speech/last` | GET | Son tanınan metin |
| `/speech/direction` | GET | Ses geliş yönü (derece) |

### Speak (TTS) — `/speak/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/speak/say` | POST | Metin sentezle ve oynat |
| `/speak/stop` | POST | Konuşmayı durdur |
| `/speak/status` | GET | TTS durumu |

### Ollama (LLM) — `/ollama/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/ollama/chat` | POST | LLM sohbet (persona + history) |
| `/ollama/translate` | POST | Metin çevirisi |
| `/ollama/personas` | GET | Mevcut kişilik listesi |

### NeoPixel — `/neopixel/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/neopixel/animate` | POST | LED animasyon tetikle |
| `/neopixel/set` | POST | Sabit renk ayarla |
| `/neopixel/off` | POST | LED'leri kapat |

### Animate — `/animate/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/animate/run` | POST | Servo animasyon çalıştır |
| `/animate/stop` | POST | Animasyonu durdur |
| `/animate/list` | GET | Mevcut animasyon listesi |

### Interactions — `/interactions/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/interactions/event` | POST | Olay bildir (event push) |
| `/interactions/metrics` | GET | Anlık metrikler |

### State Manager — `/state/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/state/get/<key>` | GET | Durum oku |
| `/state/set/<key>` | POST | Durum güncelle |
| `/state` | GET | Tüm durum |

### PiServo — `/piservo/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/piservo/set` | POST | Kulak servosunu ayarla |

### OLED Faces — `/oled/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/oled/face` | POST | Yüz ifadesi göster |
| `/oled/text` | POST | Metin göster |

### Hardware — `/hardware/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/hardware/info` | GET | CPU/RAM/sıcaklık/I2C bilgisi |

### Config Center — `/config/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/config` | GET | Config oku |
| `/config` | POST | Config güncelle |

### Diagnostics — `/diagnostics/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/diagnostics/self_test` | POST | Sistem sağlık testi başlat |
| `/diagnostics/results` | GET | Son test sonuçları |

### Scheduler — `/scheduler/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/scheduler/jobs` | GET | Zamanlanmış görevler |
| `/scheduler/jobs` | POST | Yeni görev ekle |

### Telemetry — `/telemetry/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/telemetry/metrics` | GET | Prometheus formatında metrikler |

### Notifier — `/notify/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/notify/send` | POST | Bildirim gönder (Telegram/Discord) |

### OTA — `/ota/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/ota/update` | POST | Firmware güncelleme yükle |
| `/ota/status` | GET | Güncelleme durumu |

### Logwrapper — `/logs/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/logs/stream` | WS | WebSocket log akışı |

### Calibration — `/calibration/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/calibration/start` | POST | Kalibrasyon moduna gir |
| `/calibration/set` | POST | Servo açısı gönder |
| `/calibration/save` | POST | Kalibrasyonu kaydet |

### Social DB — `/social/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/social/people` | GET | Tanınan kişiler listesi |
| `/social/person/<id>` | GET | Kişi detayı |

### ESP Link — `/esp/`
| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/esp/status` | GET | ESP32 bağlantı durumu |
| `/esp/command` | POST | ESP32'ye komut gönder |

---

## Port Haritası

| Port | Modül | Açıklama |
|------|-------|----------|
| 8080 | Gateway | Ana API hub |
| 8082 | Speech | ASR servisi (standalone) |
| 8083 | Speak | TTS servisi (standalone) |
| 8099 | Ollama Service | LLM servisi (standalone) |
| 8101 | VLM Bridge | Görsel algı servisi (standalone) |

> Not: Standalone portlar modül bağımsız çalıştırıldığında kullanılır. Gateway modunda tüm modüller 8080 portu üzerinden erişilebilir.
