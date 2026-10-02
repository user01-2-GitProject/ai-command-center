"""Bridge acceptance uses the canonical contract, not the demo lookalike."""
import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))

from acc.models import ActivityStatus, ContextMeasurement, ContextSemantic, ProviderSnapshot, SessionRecord
from acc.registry import BaseAdapter, ProviderRegistry
from live_sessions import LivePoller


class Adapter(BaseAdapter):
    provider_id = 'test'
    display_name = 'Test'

    def collect(self):
        now = time.time()
        return ProviderSnapshot('test', 'Test', 'ok', '1.0', now, sessions=[
            SessionRecord('test', 'session-1', model='gpt-5', source='file', event_time=now,
                activity=ActivityStatus.UNKNOWN,
                context=ContextMeasurement(used=1234, limit=128000,
                    semantic=ContextSemantic.LAST_REQUEST_INPUT,
                    event_time=now))])


class BridgeTests(unittest.TestCase):
    def poller(self, adapter):
        registry = ProviderRegistry()
        registry.register(adapter)
        poller = LivePoller(registry, timeout_sec=0.03)
        self.addCleanup(poller.close)
        return poller

    def test_empty_registry_is_honest(self):
        poller = LivePoller(ProviderRegistry())
        self.addCleanup(poller.close)
        poller.poll_once()
        self.assertEqual(poller.payload()['sessions'], [])
        self.assertEqual(poller.payload()['providers'], [])

    def test_disconnect_keeps_aged_cache_without_valid_occupancy_or_busy(self):
        adapter = Adapter()
        poller = self.poller(adapter)
        poller.poll_once()
        before = poller.payload()['sessions'][0]['last_update']
        adapter.collect = lambda: (_ for _ in ()).throw(RuntimeError('PRIVATE SECRET'))
        poller.poll_once()
        payload = poller.payload()
        row = payload['sessions'][0]
        self.assertTrue(row['stale'])
        self.assertEqual(row['source_status'], 'error')
        self.assertEqual(row['last_update'], before)
        self.assertIsNone(row['percent_used'])
        self.assertNotIn('PRIVATE SECRET', str(payload))
        adapter.collect = Adapter().collect
        poller.poll_once()
        self.assertEqual(poller.payload()['sessions'][0]['source_status'], 'ok')

    def test_timeout_does_not_enqueue_duplicate_reads(self):
        import threading
        release = threading.Event()
        calls = []
        adapter = Adapter()
        original = adapter.collect
        def blocked():
            calls.append(1)
            release.wait(2)
            return original()
        adapter.collect = blocked
        self.addCleanup(release.set)
        poller = self.poller(adapter)
        begin = time.monotonic()
        poller.poll_once()
        self.assertLess(time.monotonic() - begin, 0.3)
        poller.poll_once()
        self.assertEqual(len(calls), 1)
        self.assertEqual(poller.payload()['provider_states']['test']['error_kind'], 'timeout')
        release.set()
        time.sleep(0.02)
        poller.poll_once()
        self.assertEqual(poller.payload()['provider_states']['test']['status'], 'connected')

    def test_stale_event_is_not_refreshed_by_polling(self):
        from dataclasses import replace
        adapter = Adapter()
        snapshot = adapter.collect()
        row = snapshot.sessions[0]
        row.event_time = time.time() - 90
        row.context.event_time = time.time() - 400
        row.activity = ActivityStatus.BUSY
        adapter.collect = lambda: replace(snapshot, observation_time=time.time())
        poller = self.poller(adapter)
        poller.poll_once()
        result = poller.payload()['sessions'][0]
        self.assertEqual(result['session_freshness'], 'stale')
        self.assertEqual(result['context_freshness'], 'expired')
        self.assertEqual(result['activity'], 'unknown')
        self.assertTrue(result['stale'])

    def test_occupancy_requires_route_model_and_valid_measurement(self):
        adapter = Adapter()
        snapshot = adapter.collect()
        row = snapshot.sessions[0]
        row.context.semantic = ContextSemantic.OCCUPANCY
        row.context.used = 32000
        row.context.limit = 128000
        row.context.model = row.model
        row.context.route = 'https://example.invalid/v1'
        adapter.collect = lambda: snapshot
        poller = self.poller(adapter)
        poller.poll_once()
        self.assertEqual(poller.payload()['sessions'][0]['percent_used'], 25.0)
        row.context.route = None
        poller.poll_once()
        self.assertIsNone(poller.payload()['sessions'][0]['percent_used'])
        row.context.route = 'https://example.invalid/v1'
        row.context.model = 'different-model'
        poller.poll_once()
        self.assertIsNone(poller.payload()['sessions'][0]['percent_used'])

    def test_invalid_snapshot_is_redacted_and_does_not_crash(self):
        adapter = Adapter()
        adapter.collect = lambda: {'private': 'SECRET'}
        poller = self.poller(adapter)
        poller.poll_once()
        payload = poller.payload()
        self.assertEqual(payload['provider_states']['test']['error_kind'], 'invalid_snapshot')
        self.assertNotIn('SECRET', str(payload))
        self.assertEqual(payload['sessions'], [])

    def test_nonfinite_times_are_unknown_and_invalid_counts_hidden(self):
        adapter = Adapter()
        snapshot = adapter.collect()
        row = snapshot.sessions[0]
        row.event_time = float('nan')
        row.context.event_time = float('inf')
        row.context.used = -1
        adapter.collect = lambda: snapshot
        poller = self.poller(adapter)
        poller.poll_once()
        result = poller.payload()['sessions'][0]
        self.assertIsNone(result['last_update'])
        self.assertEqual(result['session_freshness'], 'unknown')
        self.assertEqual(result['context_freshness'], 'unknown')
        self.assertIsNone(result['last_request_input'])

    def test_no_credentials_paths_prompts_or_route_in_view(self):
        adapter = Adapter()
        snapshot = adapter.collect()
        snapshot.error_reason = 'PRIVATE'
        snapshot.sessions[0].context.route = 'https://user:PRIVATE@example.invalid'
        snapshot.sessions[0].prompt = 'PRIVATE'
        adapter.collect = lambda: snapshot
        poller = self.poller(adapter)
        poller.poll_once()
        self.assertNotIn('PRIVATE', str(poller.payload()))
        self.assertEqual(poller.payload()['sessions'][0]['tools'], [])

    def test_default_server_uses_canonical_manifest_not_demo_limits(self):
        from unittest.mock import patch
        from server import build_poller
        with patch('acc.registry.ProviderRegistry.load_from_manifest') as load:
            poller, mode = build_poller(False)
            self.addCleanup(poller.close)
            load.assert_called_once_with(['acc.providers.codex'])
            self.assertIsInstance(poller, LivePoller)
            self.assertEqual(mode, 'live')

    def test_historical_input_is_not_occupancy(self):
        registry = ProviderRegistry()
        registry.register(Adapter())
        poller = LivePoller(registry)
        self.addCleanup(poller.close)
        poller.poll_once()
        payload = poller.payload()
        self.assertEqual(payload['mode'], 'live')
        row = payload['sessions'][0]
        self.assertEqual(row['last_request_input'], 1234)
        self.assertIsNone(row['context_used'])
        self.assertIsNone(row['context_limit'])
        self.assertIsNone(row['percent_used'])
        self.assertEqual(row['context_semantic'], 'last_request_input')
        self.assertEqual(row['activity'], 'unknown')
        self.assertEqual(row['source_version'], '1.0')


if __name__ == '__main__':
    unittest.main()
