#!/usr/bin/env python3
"""Loopback-only isometric preview with canonical read-only telemetry.

Default: reviewed adapter manifest. --demo: explicitly labeled legacy fixtures.
No dispatch, messaging, provider-process lifecycle or provider-state writes.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import signal
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT_DIR))

from acc.providers.manifest import DEFAULT_PROVIDERS  # noqa: E402
from acc.registry import ProviderRegistry as CanonicalRegistry  # noqa: E402
from acc.server import RequestHandler as SecureHandler  # noqa: E402
from demo_support.demo import register_demo  # noqa: E402
from demo_support.poller import Poller  # noqa: E402
from demo_support.registry import ModelLimitRegistry, ProviderRegistry  # noqa: E402
from live_sessions import LivePoller  # noqa: E402

UI_DIR = APP_DIR / 'ui'
HOST = '127.0.0.1'
DEFAULT_PORT = 8471
STATIC_FILES = {
    '/': 'index.html', '/index.html': 'index.html',
    '/ui/app.js': 'app.js', '/ui/telemetry.js': 'telemetry.js', '/ui/style.css': 'style.css',
    '/ui/assets/iggy-iso.png': 'assets/iggy-iso.png',
    '/ui/assets/iggy-robot-iso.png': 'assets/iggy-robot-iso.png',
}


class Handler(SecureHandler):
    server_version = 'AICommandCenter/0.2'
    poller: Poller | LivePoller
    mode = 'live'

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, allow_nan=False).encode('utf-8')
        self._send(status, 'application/json; charset=utf-8', body)

    def _send_file(self, path):
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(UI_DIR.resolve()) or not resolved.is_file():
                raise OSError('unavailable')
            body = resolved.read_bytes()
        except (OSError, ValueError):
            self._send(404, 'text/plain; charset=utf-8', b'Asset unavailable\n')
            return
        content_type, _ = mimetypes.guess_type(str(path))
        self._send(200, content_type or 'application/octet-stream', body)

    def do_GET(self):
        if not self._host_is_local():
            self._send(421, 'text/plain; charset=utf-8', b'Misdirected request\n')
            return
        if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none') or not self._origin_is_same():
            self._send(403, 'text/plain; charset=utf-8', b'Cross-origin request denied\n')
            return
        path = urlsplit(self.path).path
        if path == '/api/sessions':
            self._send_json(self.poller.payload(self.mode))
        elif path == '/api/health':
            # HTTP shell health is not provider health or verified activity.
            self._send_json({'ok': True, 'mode': self.mode,
                             'providers': self.poller.registry.names()})
        elif path in STATIC_FILES:
            self._send_file(UI_DIR / STATIC_FILES[path])
        elif path == '/favicon.ico':
            self._send(204, 'image/x-icon', b'')
        else:
            self._send(404, 'text/plain; charset=utf-8', b'Not found\n')


def build_poller(demo=False, *, registry=None):
    try:
        interval = float(os.environ.get('ACC_POLL_SEC', '15'))
        timeout = float(os.environ.get('ACC_ADAPTER_TIMEOUT_SEC', '10'))
    except ValueError:
        raise ValueError('Polling settings must be numeric') from None
    if not demo:
        canonical = registry if registry is not None else CanonicalRegistry()
        if registry is None:
            canonical.load_from_manifest(list(DEFAULT_PROVIDERS))
        return LivePoller(canonical, interval_sec=interval, timeout_sec=timeout), 'live'
    providers, limits = ProviderRegistry(), ModelLimitRegistry()
    register_demo(providers, limits)
    return Poller(providers, limits, interval_sec=interval,
                  timeout_sec=timeout, stale_after_sec=30), 'demo'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Explicit labeled fixtures, never live')
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    try:
        port = args.port if args.port is not None else int(os.environ.get('ACC_PORT', DEFAULT_PORT))
        if not 1024 <= port <= 65535:
            raise ValueError('port')
        demo = args.demo or os.environ.get('ACC_DEMO') == '1'
        poller, mode = build_poller(demo)
    except (ValueError, OverflowError):
        parser.error('Invalid port or polling settings')
    Handler.poller, Handler.mode = poller, mode
    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True
    stop = threading.Event()
    poller.poll_once()

    def collect_loop():
        while not stop.wait(poller.interval_sec):
            poller.poll_once()

    threading.Thread(target=collect_loop, daemon=True, name='acc-poller').start()

    def shutdown(*_):
        stop.set()
        # shutdown() must not run on the serve_forever() thread (deadlock).
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    print(f'AI Command Center ({mode}) on http://{HOST}:{port}/', flush=True)
    print('Read-only providers:', ', '.join(poller.registry.names()) or '(none)', flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        stop.set()
        if isinstance(poller, LivePoller):
            poller.close()
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
