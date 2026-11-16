# MCP Client (`modules/mcp_client`)

Harici MCP (Model Context Protocol) sunucularını `stdio` JSON-RPC 2.0 alt süreçleri olarak yöneten, araç keşfini ve araç çağrılarını Gateway altında (`/mcp_client/*`) sunan modüldür.

## Temel Bileşenler

- `xMcpClientService.py` → `McpClientService`:
  - `command: "python"` gibi string komutları `shlex.split()` ile güvenli `argv` listesine ayrıştırır (`_parse_command`).
  - Tüm girişlerde (`tools`, `call`, `restart`, `connect_all_autostart`, `select_relevant_tools`) `enabled` denetimi yapar.
  - Sunucu başına `_connect_locks` kilidi kullanır; yavaş `handshake()` diğer sunucuları, `status()` ve `stop()` çağrılarını bloklamaz.
  - Üstel geri çekilme (`base_backoff_s`, `max_backoff_s`) ve devre kesici (`circuit_threshold`, `circuit_open`) uygular; Gateway `lifespan` ve `__main__.py` kapanışında `svc.stop()` otomatik çalışır.
  - `select_relevant_tools()` yalnızca bağlı sunucuları tarar ve araç embedding'lerini `_tool_embed_cache` içinde önbellekler.
- `services/stdio_process.py` → `StdioMcpConnection`:
  - `_reader_loop` `finally:` bloğu EOF/çökme halinde `alive=False` ve `_fail_all_pending("eof")` çalıştırarak bekleyen çağrıları anında uyandırır; `RequestTimeout` sonrasında asılı süreç temizlenir.
- `config_loader.py` → `modules.common.config_loader.load_module_config()` aracılığıyla `config/agent.yaml` ve `MCP_CLIENT_HOST` bağlama ayarlarını birleştirir.

## API (`/mcp_client/*`)

- `GET /mcp_client/healthz`, `GET /mcp_client/status`
- `POST /mcp_client/autostart`, `POST /mcp_client/stop`, `POST /mcp_client/stop/{server}`, `POST /mcp_client/restart/{server}`
- `GET /mcp_client/tools`, `GET /mcp_client/tools/{server}`, `POST /mcp_client/call`
