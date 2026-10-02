"""Owned ephemeral fixture server + isolated Chromium; never real telemetry."""
import os
import pathlib
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))
from acc.models import ActivityStatus, ContextMeasurement, ContextSemantic, ProviderSnapshot, SessionRecord
from acc.registry import BaseAdapter, ProviderRegistry
from live_sessions import LivePoller
from server import Handler


class BrowserFixture(BaseAdapter):
    provider_id = 'fixture'
    display_name = 'Synthetic fixture (not actual source)'

    def collect(self):
        now = time.time()
        return ProviderSnapshot(self.provider_id, self.display_name, 'ok', 'fixture-1', now,
            sessions=[SessionRecord(self.provider_id, f'fixture-{i}', model='fixture-model',
                source='synthetic-fixture', event_time=now-2, started_at=now-100,
                activity=ActivityStatus.UNKNOWN,
                context=ContextMeasurement(ContextSemantic.LAST_REQUEST_INPUT, 10, 100,
                    'fixture-model', None, now-3)) for i in range(8)])


def main():
    # A distinct output directory is mandatory: preserve original evidence.
    out = pathlib.Path(sys.argv[1]).resolve()
    allowed = ROOT / 'docs/verification/live-session-bridge/fix-cycle-1'
    if not out.is_relative_to(allowed):
        raise ValueError('Fixture receipts must be inside fix-cycle-1')
    registry = ProviderRegistry()
    registry.register(BrowserFixture())
    poller = LivePoller(registry)
    poller.poll_once()
    class FixtureHandler(Handler):
        def log_message(self, *_):
            pass
    FixtureHandler.poller, FixtureHandler.mode = poller, 'live'
    server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    env = {**os.environ, 'ACC_QA_URL': f'http://127.0.0.1:{server.server_port}',
           'ACC_QA_OUT': str(out), 'ACC_QA_FIXTURE': '1'}
    try:
        return subprocess.run(['node', 'app/tests/browser-live.cjs'], cwd=ROOT, env=env, timeout=120).returncode
    finally:
        server.shutdown()
        server.server_close()
        poller.close()
        worker.join(2)


if __name__ == '__main__':
    raise SystemExit(main())
