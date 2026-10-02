"""Contract tests for the shared telemetry contract (ACC-08).

Executable proof of the registry rules: providers can be added and
subtracted with no shell/UI change, limits come only from the limit
registry, percent is never guessed, and one bad adapter cannot break the
poll.
"""
import sys
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo_support import (AdapterError, AdapterReading, ModelLimitRegistry, Poller,
                 ProviderRegistry, utcnow)


def reading(provider="p", session="s1", model="m1", used=1000,
            activity="working", age_sec=5, **kw):
    return AdapterReading(
        provider=provider, session_id=session, model=model,
        activity=activity, context_used=used,
        source="test", observed_at=utcnow() - timedelta(seconds=age_sec),
        **kw)


class DummyAdapter:
    def __init__(self, name="dummy", readings=None, exc=None, delay=0):
        self.name = name
        self._readings = readings or []
        self._exc = exc
        self._delay = delay
        self.read_calls = 0

    def read(self):
        self.read_calls += 1
        if self._delay:
            time.sleep(self._delay)
        if self._exc:
            raise self._exc
        return self._readings


def make_poller(**kw):
    kw.setdefault("timeout_sec", 5)
    return Poller(ProviderRegistry(), ModelLimitRegistry(), **kw)


class RegistryContractTest(unittest.TestCase):
    def test_register_appears_unregister_disappears(self):
        """The executable proof: add/remove a provider with no shell/UI change."""
        poller = make_poller()
        adapter = DummyAdapter(readings=[reading()])
        poller.registry.register("dummy", adapter)
        poller.poll_once()
        names = [p["provider"] for p in poller.payload("live")["providers"]]
        self.assertIn("dummy", names)
        self.assertEqual(len(poller.payload("live")["providers"][0]["sessions"]), 1)

        poller.registry.unregister("dummy")
        poller.poll_once()
        names = [p["provider"] for p in poller.payload("live")["providers"]]
        self.assertNotIn("dummy", names)

    def test_register_rejects_empty_name(self):
        poller = make_poller()
        with self.assertRaises(ValueError):
            poller.registry.register("  ", DummyAdapter())

    def test_unregister_missing_is_safe(self):
        poller = make_poller()
        poller.registry.unregister("never-registered")  # must not raise


class LimitRegistryTest(unittest.TestCase):
    def test_unknown_model_yields_no_percent_never_a_guess(self):
        poller = make_poller()
        poller.registry.register("p", DummyAdapter(
            readings=[reading(model="mystery-model-9", used=12345)]))
        poller.poll_once()
        s = poller.payload("live")["providers"][0]["sessions"][0]
        self.assertIsNone(s["percent_used"])
        self.assertIsNone(s["context_limit"])
        self.assertIn("mystery-model-9", s["unavailable_reason"])
        self.assertEqual(s["context_used"], 12345)  # used still shown

    def test_zero_limit_rejected(self):
        limits = ModelLimitRegistry()
        with self.assertRaises(ValueError):
            limits.set_limit("p", "m", 0)

    def test_percent_only_from_matching_pair(self):
        poller = make_poller()
        poller.limits.set_limit("p", "m1", 2000)
        poller.registry.register("p", DummyAdapter(readings=[
            reading(session="ok", model="m1", used=1000),          # 50%
            reading(session="no-used", model="m1", used=None),    # no numerator
            reading(session="unknown-model", model="mX", used=10),  # no denominator
        ]))
        poller.poll_once()
        by_id = {s["session_id"]: s
                 for s in poller.payload("live")["providers"][0]["sessions"]}
        self.assertEqual(by_id["ok"]["percent_used"], 50)
        self.assertIsNone(by_id["no-used"]["percent_used"])
        self.assertIsNone(by_id["unknown-model"]["percent_used"])


class FreshnessTest(unittest.TestCase):
    def test_stale_threshold(self):
        poller = make_poller(stale_after_sec=60)
        poller.registry.register("p", DummyAdapter(readings=[
            reading(session="fresh", age_sec=59),
            reading(session="stale", age_sec=61),
        ]))
        poller.poll_once()
        by_id = {s["session_id"]: s
                 for s in poller.payload("live")["providers"][0]["sessions"]}
        self.assertEqual(by_id["fresh"]["freshness"], "fresh")
        self.assertEqual(by_id["stale"]["freshness"], "stale")

    def test_lifecycle_status_separate_from_freshness(self):
        """Unknown activity is never silently zeroed; freshness is independent."""
        poller = make_poller()
        poller.registry.register("p", DummyAdapter(
            readings=[reading(activity="unknown", age_sec=5)]))
        poller.poll_once()
        s = poller.payload("live")["providers"][0]["sessions"][0]
        self.assertEqual(s["activity"], "unknown")
        self.assertEqual(s["freshness"], "fresh")


class IsolationTest(unittest.TestCase):
    def test_provider_error_does_not_erase_healthy_providers(self):
        poller = make_poller()
        poller.registry.register("good", DummyAdapter(readings=[reading()]))
        poller.registry.register(
            "bad", DummyAdapter(exc=AdapterError("sqlite database locked")))
        poller.poll_once()
        by_name = {p["provider"]: p for p in poller.payload("live")["providers"]}
        self.assertTrue(by_name["good"]["ok"])
        self.assertEqual(len(by_name["good"]["sessions"]), 1)
        self.assertFalse(by_name["bad"]["ok"])
        self.assertIn("locked", by_name["bad"]["error"])
        self.assertEqual(by_name["bad"]["sessions"], [])

    def test_malformed_adapter_output_is_contained(self):
        class BadShape:
            name = "badshape"

            def read(self):
                return {"not": "a list"}

        poller = make_poller()
        poller.registry.register("good", DummyAdapter(readings=[reading()]))
        poller.registry.register("badshape", BadShape())
        poller.poll_once()
        by_name = {p["provider"]: p for p in poller.payload("live")["providers"]}
        self.assertTrue(by_name["good"]["ok"])
        self.assertFalse(by_name["badshape"]["ok"])
        self.assertIn("malformed", by_name["badshape"]["error"])

    def test_unexpected_adapter_crash_is_contained(self):
        class Crasher:
            name = "crasher"

            def read(self):
                raise RuntimeError("boom")

        poller = make_poller()
        poller.registry.register("good", DummyAdapter(readings=[reading()]))
        poller.registry.register("crasher", Crasher())
        poller.poll_once()
        by_name = {p["provider"]: p for p in poller.payload("live")["providers"]}
        self.assertTrue(by_name["good"]["ok"])
        self.assertFalse(by_name["crasher"]["ok"])

    def test_slow_adapter_times_out_without_blocking_others(self):
        poller = make_poller(timeout_sec=1)
        poller.registry.register("fast", DummyAdapter(readings=[reading()]))
        poller.registry.register("slow", DummyAdapter(delay=3))
        start = time.monotonic()
        poller.poll_once()
        elapsed = time.monotonic() - start
        by_name = {p["provider"]: p for p in poller.payload("live")["providers"]}
        self.assertTrue(by_name["fast"]["ok"])
        self.assertFalse(by_name["slow"]["ok"])
        self.assertIn("timed out", by_name["slow"]["error"])
        self.assertLess(elapsed, 10)  # the 3s sleeper must not serialize the poll

    def test_polls_do_not_overlap(self):
        poller = make_poller()
        adapter = DummyAdapter(readings=[reading()], delay=0.5)
        poller.registry.register("p", adapter)
        t = threading.Thread(target=poller.poll_once)
        t.start()
        time.sleep(0.1)
        poller.poll_once()  # must skip: a poll is already running
        t.join()
        self.assertEqual(adapter.read_calls, 1)


if __name__ == "__main__":
    unittest.main()
