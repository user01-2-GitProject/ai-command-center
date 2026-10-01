"""Small loopback-only HTTP shell. Provider adapters are added in later tasks."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlsplit


DEFAULT_PORT = 8765
MAX_PORT = 65535
MIN_PORT = 1024
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def snapshot() -> dict[str, object]:
    """Return an honest empty state until a verified provider is configured."""
    return {
        "status": "not_connected",
        "observed_at": None,
        "sessions": [],
        "reason": "No provider adapters are configured yet.",
    }


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, _format: str, *_args: object) -> None:
        # Request paths and headers are unnecessary for this metadata-only shell.
        return

    def _host_is_local(self) -> bool:
        expected_port = self.server.server_address[1]
        return self.headers.get("Host", "").lower() in {
            f"127.0.0.1:{expected_port}",
            f"localhost:{expected_port}",
        }

    def _origin_is_same(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        host = self.headers.get("Host", "").lower()
        return origin == f"http://{host}"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._host_is_local():
            self._send(421, "text/plain; charset=utf-8", b"Misdirected request\n")
            return

        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site not in (None, "same-origin", "none") or not self._origin_is_same():
            self._send(403, "text/plain; charset=utf-8", b"Cross-origin request denied\n")
            return

        path = urlsplit(self.path).path
        if path == "/api/snapshot":
            body = json.dumps(snapshot(), separators=(",", ":")).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return

        asset = STATIC_FILES.get(path)
        if asset is None:
            self._send(404, "text/plain; charset=utf-8", b"Not found\n")
            return

        filename, content_type = asset
        body = files("acc").joinpath("static", filename).read_bytes()
        self._send(200, content_type, body)

    def do_HEAD(self) -> None:
        self._send(405, "text/plain; charset=utf-8", b"Method not allowed\n")

    def do_POST(self) -> None:
        self._send(405, "text/plain; charset=utf-8", b"Method not allowed\n")


def create_server(port: int = DEFAULT_PORT) -> DashboardServer:
    if isinstance(port, bool) or not isinstance(port, int) or not MIN_PORT <= port <= MAX_PORT:
        raise ValueError(f"port must be an integer from {MIN_PORT} to {MAX_PORT}")
    return DashboardServer(("127.0.0.1", port), RequestHandler)


def main() -> None:
    raw_port = os.environ.get("ACC_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
        server = create_server(port)
    except (ValueError, OverflowError) as error:
        raise SystemExit(f"Invalid ACC_PORT: {error}") from None

    host, bound_port = server.server_address
    print(f"AI Command Center listening at http://{host}:{bound_port}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping AI Command Center.")
    finally:
        server.server_close()
