#!/usr/bin/env python3
"""AI Command Center local server (ACC-07/ACC-12).

Loopback-only HTTP server. Serves the dashboard UI and one JSON API backed
by the provider registry. Read-only: no endpoint writes, dispatches, or
messages anything.

Usage:
    python3 app/server.py [--demo] [--port 8471]

    --demo      register the labeled demo fixtures (SAMPLE DATA banner)
    ACC_DEMO=1  same via environment
    ACC_PORT    override the port (default 8471)
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acc.demo import register_demo  # noqa: E402
from acc.poller import Poller  # noqa: E402
from acc.registry import ModelLimitRegistry, ProviderRegistry  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
UI_DIR = APP_DIR / "ui"
HOST = "127.0.0.1"
DEFAULT_PORT = 8471


class Handler(BaseHTTPRequestHandler):
    server_version = "AICommandCenter/0.1"

    # set by main()
    poller: Poller
    mode: str = "live"

    def log_message(self, fmt, *args):  # quieter logs
        sys.stderr.write("acc: " + fmt % args + "\n")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")  # json escapes HTML in strings
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        ctype, _ = mimetypes.guess_type(str(path))
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send_file(UI_DIR / "index.html")
        elif self.path == "/api/sessions":
            self._send_json(self.poller.payload(self.mode))
        elif self.path == "/api/health":
            self._send_json({"ok": True, "mode": self.mode,
                             "providers": self.poller.registry.names()})
        elif self.path.startswith("/ui/"):
            rel = self.path[len("/ui/"):]
            # path safety: no traversal, only files under UI_DIR
            if ".." in rel or rel.startswith("/") or not rel:
                self.send_error(404)
                return
            path = (UI_DIR / rel).resolve()
            if not str(path).startswith(str(UI_DIR.resolve())) or not path.is_file():
                self.send_error(404)
                return
            self._send_file(path)
        else:
            self.send_error(404)

    # No POST/PUT/DELETE handlers: the server is read-only by construction.


def build_poller(demo: bool) -> tuple[Poller, str]:
    registry = ProviderRegistry()
    limits = ModelLimitRegistry()
    mode = "live"
    if demo:
        register_demo(registry, limits)
        mode = "demo"
    interval = int(os.environ.get("ACC_POLL_SEC", "15"))
    timeout = int(os.environ.get("ACC_ADAPTER_TIMEOUT_SEC", "10"))
    stale_after = int(os.environ.get("ACC_STALE_AFTER_SEC", "60"))
    poller = Poller(registry, limits, interval_sec=interval,
                    timeout_sec=timeout, stale_after_sec=stale_after)
    return poller, mode


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Command Center local server")
    ap.add_argument("--demo", action="store_true",
                    help="register labeled demo fixtures (SAMPLE DATA banner)")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("ACC_PORT", DEFAULT_PORT)))
    args = ap.parse_args()

    demo = args.demo or os.environ.get("ACC_DEMO") == "1"
    poller, mode = build_poller(demo)
    poller.poll_once()  # populate before first request

    Handler.poller = poller
    Handler.mode = mode

    stop = threading.Event()

    def loop():
        while not stop.wait(poller.interval_sec):
            poller.poll_once()

    thread = threading.Thread(target=loop, daemon=True, name="acc-poller")
    thread.start()

    server = ThreadingHTTPServer((HOST, args.port), Handler)
    bound = server.socket.getsockname()
    print(f"AI Command Center ({mode} mode) on http://{bound[0]}:{bound[1]}",
          flush=True)
    print("Providers:", ", ".join(poller.registry.names()) or "(none — "
          "live mode, nothing connected yet)", flush=True)
    if demo:
        print("DEMO MODE: all data is labeled sample fixtures.", flush=True)

    def shutdown(*_):
        stop.set()
        server.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
