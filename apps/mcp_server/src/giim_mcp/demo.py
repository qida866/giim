"""受控本地 REST 服务，响应形状与已检查的 GIIM 路由一致。"""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .fixtures import CAPS, RECORDS, STAMP, select


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/v1/ready":
            self.reply({"status": "ready", "database": True, "vectors": True})
        elif path == "/api/v1/coverage":
            self.reply(
                {
                    "window_hours": 24,
                    "observed_at": STAMP,
                    "reporting_languages": ["en", "zh", "es", "fr"],
                    "observed_publishers": 4,
                    "current_articles": 18,
                    "publisher_regions": {"synthetic": 18},
                    "coverage_basis": "Authored synthetic fixture; not global coverage",
                }
            )
        elif path == "/api/v1/events/today":
            self.reply({"events": [r["event"] for r in RECORDS], "total_events": len(RECORDS)})
        elif path.startswith("/api/v1/events/"):
            found = next((r for r in RECORDS if r["event"]["id"] == path.rsplit("/", 1)[1]), None)
            self.reply(found or {"detail": "not found"}, 200 if found else 404)
        else:
            self.reply({"detail": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/api/v1/search/events":
            return self.reply({"detail": "forbidden"}, 403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 2048:
                return self.reply({"detail": "too large"}, 422)
            body = json.loads(self.rfile.read(length))
            rows = select(body["query"])[: body.get("top_k", 10)]
            self.reply(
                {
                    "query": body["query"],
                    "events": [r["event"] for r in rows],
                    "reports": [],
                    "ranking_basis": "authored deterministic fixture routing",
                }
            )
        except (ValueError, KeyError, TypeError):
            self.reply({"detail": "invalid request"}, 422)

    def reply(self, data: dict | list, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@contextmanager
def demo_api():
    """只绑定随机回环端口；退出时关闭线程和套接字。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", CAPS
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
