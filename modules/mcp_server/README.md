# MCP Server (`modules/mcp_server`)

SentryBOT'un Gateway REST uçlarını dış MCP istemcilerine JSON-RPC 2.0 (`stdio` veya `/mcp/*` HTTP) araç ve salt-okunur kaynak (`resources/*`) olarak sunan adaptördür.

## Temel Yetenekler

- `xMcpServerService.py` → `xMcpServerService`:
  - Kalıcı `requests.Session()` paylaşımı.
  - `param_in` sözleşmesi (`query`, `json`, `body`): `set_lights` (`/neopixel/fill` `r_`, `g`, `b`, `segment` query parametreleri) ve `lights_effect` (`/neopixel/{effect}` `wait`, `cycles` query) ile `arduino_send` (`/arduino/send` üst düzey JSON gövdesi) canlı router'larla birebir eşleşir.
  - Zorunlu alan/tip şema doğrulaması ve path-traversal koruması (`resolve_path_pure`).
  - Güvenlik profili: `read_only: bool` ve `allowed_tools: [...]` ile donanım yazma araçları kısıtlanabilir; `resources/list` ve `resources/read` ile `sentrybot://autonomy/state` ve `sentrybot://persona/active` sunulur.
- `services/protocol.py` → `McpProtocol` & `run_stdio`:
  - `initialize` öncesi `tools/*` ve `resources/*` çağrılarını `-32002` (`server_not_initialized`) ile reddeder; bozuk JSON satırlarında `-32700` (`parse_error`) döner; yapılandırılmış JSON sonuçlarını `structuredContent` ile korur.
- `__main__.py`: Tüm Python log çıkışını `sys.stderr`'a zorlayarak `stdout` JSON-RPC akımını korur.
- `api/router.py`: Gateway altında `/mcp/healthz`, `/mcp/status`, `/mcp/tools`, `/mcp/resources`, `/mcp/resources/read` uçlarını sunar.
- `config_loader.py`: `modules.common.config_loader.load_module_config()` ile `config/agent.yaml` + `@gateway` URL çözümlemesini kullanır.
