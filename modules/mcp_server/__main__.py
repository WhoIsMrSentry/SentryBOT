from __future__ import annotations

import sys

from modules.mcp_server.config_loader import load_config
from modules.mcp_server.xMcpServerService import xMcpServerService
from modules.mcp_server.services.protocol import McpProtocol, run_stdio


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cfg_path = None
    if argv and argv[0] in ("-c", "--config") and len(argv) > 1:
        cfg_path = argv[1]
    cfg = load_config(cfg_path)
    service = xMcpServerService(cfg)
    protocol = McpProtocol(service)
    return run_stdio(protocol)


if __name__ == "__main__":
    raise SystemExit(main())
