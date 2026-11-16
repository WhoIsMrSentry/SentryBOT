from __future__ import annotations

from contextlib import asynccontextmanager
import fastapi
import uvicorn

from modules.mcp_client.api.router import get_router
from modules.mcp_client.config_loader import load_config
from modules.mcp_client.xMcpClientService import McpClientService


def main() -> int:
    cfg = load_config()
    svc = McpClientService(cfg)

    @asynccontextmanager
    async def lifespan(_app: fastapi.FastAPI):
        svc.connect_all_autostart()
        try:
            yield
        finally:
            svc.stop()

    app = fastapi.FastAPI(title="SentryBOT MCP Client", lifespan=lifespan)
    app.include_router(get_router(svc))
    mcp_cfg = (cfg.get("mcp_client") or {}) if isinstance(cfg.get("mcp_client"), dict) else {}
    srv_cfg = mcp_cfg.get("server") if isinstance(mcp_cfg.get("server"), dict) else {}
    host = str(srv_cfg.get("host") or mcp_cfg.get("host") or "127.0.0.1")
    port = int(srv_cfg.get("port") or mcp_cfg.get("port") or 8088)
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
