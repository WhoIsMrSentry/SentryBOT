# Skill: Module Dependency Map — Modül Bağımlılık Haritalama

> Modüller arası bağımlılıkları analiz etme ve haritalama prosedürü.

## Analiz Prosedürü

### Adım 1: Import Taraması
```bash
# Modülün hangi diğer modülleri import ettiğini bul
grep -r "from modules\." modules/{{MODULE_NAME}}/ --include="*.py" | grep -v __pycache__
grep -r "import modules\." modules/{{MODULE_NAME}}/ --include="*.py" | grep -v __pycache__
```

### Adım 2: HTTP Çağrı Taraması
```bash
# Modülün hangi endpoint'leri çağırdığını bul
grep -rn "localhost:8080\|/arduino/\|/speak/\|/neopixel/\|/ollama/\|/vlm/\|/state/" \
  modules/{{MODULE_NAME}}/ --include="*.py" | grep -v __pycache__
```

### Adım 3: Config Bağımlılık Taraması
```bash
# Config'de referans verilen URL'leri bul
grep -n "endpoint\|url\|host\|port" modules/{{MODULE_NAME}}/config/config.yml
```

### Adım 4: Bağımlılık Diyagramı Oluştur

```mermaid
graph LR
    {{MODULE_NAME}} --> |HTTP| modül_a
    {{MODULE_NAME}} --> |Serial| modül_b
    modül_c --> |HTTP| {{MODULE_NAME}}
```

## Bağımlılık Türleri

| Tür | Açıklama | Örnek |
|-----|----------|-------|
| **Doğrudan** | Import ile | `from modules.x import Y` |
| **HTTP** | API çağrısı ile | `POST /speak/say` |
| **Serial** | Arduino kontratı ile | `contract.build_set_servo()` |
| **Config** | Config referansı ile | `endpoint: http://localhost:8080/x` |
| **Event** | Olay bildirimi ile | `POST /interactions/event` |

## Çıktı Formatı
Bağımlılık haritası MCP `trace_path` ile doğrulanır, `index_repository` ile güncellenir.
