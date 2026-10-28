from __future__ import annotations

import uvicorn

from modules.mcp_client.api.router import get_router
from modules.mcp_client.config_loader import load_config
from modules.mcp_client.xMcpClientService import McpClientService


def main() -> int:
    cfg = load_config()
    svc = McpClientService(cfg)
    svc.connect_all_autostart()

    import fastapi

    app = fastapi.FastAPI(title="SentryBOT MCP Client")
    app.include_router(get_router(svc))
    mcp_cfg = (cfg.get("mcp_client") or {}) if isinstance(cfg.get("mcp_client"), dict) else {}
    host = str(mcp_cfg.get("host", "127.0.0.1"))
    port = int(mcp_cfg.get("port", 8088))
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
