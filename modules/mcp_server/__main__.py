from __future__ import annotations

import logging
import sys

# Ensure JSON-RPC stdout stays unpolluted; all diagnostics go strictly to stderr.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    force=True,
)

from modules.mcp_server.config_loader import load_config  # noqa: E402
from modules.mcp_server.services.protocol import McpProtocol, run_stdio  # noqa: E402
from modules.mcp_server.xMcpServerService import xMcpServerService  # noqa: E402


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
