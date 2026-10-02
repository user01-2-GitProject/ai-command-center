"""Deterministic consumer regressions; synthetic metadata, never real sources."""
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))
from acc.models import ActivityStatus, ContextMeasurement, ContextSemantic, ProviderSnapshot, SessionRecord
from acc.registry import BaseAdapter, ProviderRegistry
from live_sessions import LivePoller, session_view, timestamp

NOW = 1790884800.0


class FixtureAdapter(BaseAdapter):
    @property
    def display_name(self):
        return 'Synthetic fixture'

    @property
    def provider_id(self):
        return self._pid

    def __init__(self, pid):
        self._pid = pid
        self.snapshot = ProviderSnapshot(pid, self.display_name, 'ok', 'fixture', NOW, sessions=[
            SessionRecord(pid, 'fixture-session', model='fixture-model', event_time=NOW - 2,
                started_at=NOW - 100, activity=ActivityStatus.BUSY,
                context=ContextMeasurement(ContextSemantic.OCCUPANCY, 10, 100,
                    'fixture-model', 'fixture-route', NOW - 3))])

    def collect(self):
        return self.snapshot


class NumericRegressions(unittest.TestCase):
    @patch('acc.models.time.time', return_value=NOW)
    def test_occupancy_uses_validated_context_freshness(self, _clock):
        adapter = FixtureAdapter('fixture')
        row = adapter.snapshot.sessions[0]
        for value, freshness in [(str(NOW - 3), 'unknown'), (True, 'unknown'),
                                 (NOW + 1, 'unknown'), (NOW - 301, 'expired')]:
            with self.subTest(value=value):
                row.context.event_time = value
                result = session_view(row, adapter.snapshot, NOW)
                self.assertEqual(result['context_freshness'], freshness)
                self.assertIsNone(result['percent_used'])
                self.assertIsNone(result['context_used'])
        for age in (0, 30, 31, 300):
            row.context.event_time = NOW - age
            self.assertEqual(session_view(row, adapter.snapshot, NOW)['percent_used'], 10.0)

    @patch('acc.models.time.time', return_value=NOW)
    def test_oversized_telemetry_is_bounded_before_math(self, _clock):
        for field in ['context_time', 'event_time', 'started_at', 'observation_time', 'used', 'limit']:
            with self.subTest(field=field):
                adapter = FixtureAdapter('fixture')
                snap, row = adapter.snapshot, adapter.snapshot.sessions[0]
                if field == 'context_time':
                    row.context.event_time = 10**1000
                elif field in ('used', 'limit'):
                    setattr(row.context, field, 10**1000)
                elif field == 'observation_time':
                    snap.observation_time = 10**1000
                else:
                    setattr(row, field, 10**1000)
                result = session_view(row, snap, NOW)
                json.dumps(result, allow_nan=False)
                if field in ('context_time', 'used', 'limit', 'observation_time'):
                    self.assertIsNone(result['percent_used'])
        for value in [10**1000, -(10**1000), float('inf'), float('nan'), True, str(NOW)]:
            self.assertIsNone(timestamp(value))

    def test_serialization_failure_is_contained_per_provider(self):
        registry = ProviderRegistry()
        registry.register(FixtureAdapter('broken'))
        registry.register(FixtureAdapter('healthy'))
        poller = LivePoller(registry)
        self.addCleanup(poller.close)
        poller.poll_once()
        original = session_view
        for failure in ('exception', 'unserializable', 'nonfinite'):
            def broken(row, snapshot, now):
                if snapshot.provider_id != 'broken':
                    return original(row, snapshot, now)
                if failure == 'exception':
                    raise OverflowError('PRIVATE ERROR')
                return {**original(row, snapshot, now), 'invalid': object() if failure == 'unserializable' else float('nan')}
            with self.subTest(failure=failure), patch('live_sessions.session_view', broken), patch('live_sessions.time.time', return_value=NOW):
                payload = poller.payload()
                serialized = json.dumps(payload, allow_nan=False)
                self.assertNotIn('PRIVATE', serialized)
                self.assertEqual([s['provider_id'] for s in payload['sessions']], ['healthy'])
                self.assertEqual(payload['provider_states']['broken']['status'], 'error')
                self.assertEqual(payload['provider_states']['broken']['error_kind'], 'serialization_error')
                self.assertEqual(payload['providers'][0]['sessions'], [])


class RetirementRegressions(unittest.TestCase):
    def make_poller(self):
        registry = ProviderRegistry()
        registry.register(FixtureAdapter('fixture'))
        poller = LivePoller(registry, timeout_sec=0.01)
        self.addCleanup(poller.close)
        return registry, poller

    def test_completed_removed_reader_and_cache_are_reaped(self):
        registry, poller = self.make_poller()
        poller.poll_once()
        # A read can finish after the timeout but before unregistration.
        from concurrent.futures import Future
        future = Future()
        future.set_result(registry.get('fixture').snapshot)
        poller._inflight['fixture'] = (registry.get('fixture'), future)
        registry.unregister('fixture')
        poller.poll_once()
        self.assertNotIn('fixture', poller._inflight)
        self.assertNotIn('fixture', poller._snapshots)
        self.assertNotIn('fixture', poller._last_success)
        self.assertEqual(poller.payload()['sessions'], [])

    def test_retired_hung_read_never_waits_or_duplicates_on_reregistration(self):
        registry, poller = self.make_poller()
        poller.poll_once()
        # Don't launch a truly hung daemon: hold its Future deterministically.
        with patch('live_sessions.threading.Thread.start') as start:
            poller.poll_once()
            self.assertEqual(start.call_count, 1)
            original, future = poller._inflight['fixture']
            registry.unregister('fixture')
            with patch('live_sessions.wait', side_effect=AssertionError('retired read spent poll timeout')):
                poller.poll_once()
                self.assertNotIn('fixture', poller._inflight)
                self.assertNotIn('fixture', poller._snapshots)
                self.assertNotIn('fixture', poller._last_success)
                # Same instance and replacement must both respect the hung read.
                for adapter in (original, FixtureAdapter('fixture')):
                    registry.register(adapter)
                    poller.poll_once()
                    self.assertEqual(start.call_count, 1)
                    self.assertEqual(poller.payload()['sessions'], [])
                    registry.unregister('fixture')
                    poller.poll_once()
            future.set_result(original.snapshot)
            self.assertEqual(poller._retired, {}, 'completion reaps retired results without another poll')
            registry.register(FixtureAdapter('fixture'))
            poller.poll_once()
            self.assertEqual(start.call_count, 2, 'new read allowed only after the retired read finishes')
            poller._inflight['fixture'][1].set_result(registry.get('fixture').snapshot)
            with patch('live_sessions.time.time', return_value=NOW):
                poller.poll_once()
                self.assertEqual(poller.payload()['provider_states']['fixture']['status'], 'connected')

    def test_completion_during_callback_registration_does_not_deadlock(self):
        from concurrent.futures import Future
        import threading
        registry, poller = self.make_poller()
        adapter = registry.get('fixture')
        assert isinstance(adapter, FixtureAdapter)

        class CompletingFuture(Future):
            def add_done_callback(self, fn):
                # Completion between publishing retirement and attaching cleanup.
                self.set_result(adapter.snapshot)
                super().add_done_callback(fn)

        future = CompletingFuture()
        poller._inflight['fixture'] = (adapter, future)
        registry.unregister('fixture')
        errors = []
        def retire():
            try:
                poller.poll_once()
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=retire, daemon=True)
        worker.start()
        worker.join(0.5)
        self.assertFalse(worker.is_alive(), 'synchronous done callback deadlocked retirement')
        self.assertEqual(errors, [])
        self.assertTrue(future.done(), 'retirement must attach completion cleanup')
        self.assertEqual(poller._retired, {})
        self.assertEqual(poller._inflight, {})

    def test_failed_retired_completion_releases_reader_and_result_references(self):
        import gc
        import weakref
        registry, poller = self.make_poller()
        adapter = registry.get('fixture')
        adapter_ref = weakref.ref(adapter)
        with patch('live_sessions.threading.Thread.start'):
            poller.poll_once()
        future = poller._inflight['fixture'][1]
        future_ref = weakref.ref(future)
        registry.unregister('fixture')
        poller.poll_once()
        del adapter
        gc.collect()
        self.assertIsNone(adapter_ref(), 'retirement need not retain the adapter')
        future.set_exception(RuntimeError('synthetic failure'))
        self.assertEqual(poller._retired, {}, 'failed completion also reaps without polling')
        del future
        gc.collect()
        self.assertIsNone(future_ref(), 'completed retirement must not retain its Future')
        self.assertEqual(poller._snapshots, {})
        self.assertEqual(poller._last_success, {})


if __name__ == '__main__':
    unittest.main()
