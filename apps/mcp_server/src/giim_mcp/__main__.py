"""启动入口；stdout 仅用于 stdio 协议。"""

import argparse
import logging
import os
import sys

from .http import create_http_app
from .server import create_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    server = create_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        import uvicorn

        app = create_http_app(
            server,
            args.host,
            args.port,
            os.getenv("GIIM_MCP_TOKEN"),
            tuple(filter(None, os.getenv("GIIM_MCP_ORIGINS", "").split(","))),
            os.getenv("GIIM_MCP_PUBLIC_HOST"),
        )
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
