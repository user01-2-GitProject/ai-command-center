"""ACC-08 contract tests: shared model, provider registry and limit registry.

Covers every acceptance-checklist item:
- Normalized session/snapshot model fields and defaults
- Freshness thresholds (fresh / stale / expired / unknown)
- Context percentage rules (only from occupancy + matching model+route + fresh)
- Provider registry add/remove pluggability contract
- Context-limit registry: static, observed, unknown-model, route normalization
- Malformed inputs, missing limits, zero limits, stale/expired suppression
- Adapters cannot execute instructions from telemetry (data-not-code check)
"""

from __future__ import annotations

import time
import unittest

from acc.limits import ContextLimitRegistry, LimitResult
from acc.models import (
    ActivityStatus,
    ContextMeasurement,
    ContextSemantic,
    FreshnessStatus,
    ProviderSnapshot,
    SessionRecord,
    STALE_SECONDS,
    EXPIRED_SECONDS,
    freshness_of,
)
from acc.registry import BaseAdapter, ProviderRegistry, ProviderSnapshot as _PS


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class _DummyAdapter(BaseAdapter):
    """Minimal adapter used to test the registry contract."""

    def __init__(self, pid: str = "dummy", name: str = "Dummy Provider") -> None:
        self._pid = pid
        self._name = name
        self.collect_calls: int = 0

    @property
    def provider_id(self) -> str:
        return self._pid

    @property
    def display_name(self) -> str:
        return self._name

    def collect(self) -> ProviderSnapshot:
        self.collect_calls += 1
        return ProviderSnapshot(
            provider_id=self._pid,
            display_name=self._name,
            source_status="ok",
            observation_time=time.time(),
        )


# ---------------------------------------------------------------------------
# Freshness tests
# ---------------------------------------------------------------------------

class FreshnessTests(unittest.TestCase):

    def _now(self) -> float:
        return time.time()

    def test_fresh_within_threshold(self) -> None:
        now = self._now()
        event = now - STALE_SECONDS + 1
        self.assertEqual(freshness_of(event, now), FreshnessStatus.FRESH)

    def test_stale_between_thresholds(self) -> None:
        now = self._now()
        event = now - STALE_SECONDS - 1
        self.assertEqual(freshness_of(event, now), FreshnessStatus.STALE)

    def test_expired_beyond_threshold(self) -> None:
        now = self._now()
        event = now - EXPIRED_SECONDS - 1
        self.assertEqual(freshness_of(event, now), FreshnessStatus.EXPIRED)

    def test_none_timestamp_is_unknown(self) -> None:
        self.assertEqual(freshness_of(None), FreshnessStatus.UNKNOWN)

    def test_future_timestamp_is_unknown(self) -> None:
        now = time.time()
        self.assertEqual(freshness_of(now + 3600, now), FreshnessStatus.UNKNOWN)

    def test_non_numeric_timestamp_is_unknown(self) -> None:
        self.assertEqual(freshness_of("2026-09-29"), FreshnessStatus.UNKNOWN)  # type: ignore[arg-type]

    def test_boundary_exactly_at_stale_threshold(self) -> None:
        now = self._now()
        self.assertEqual(freshness_of(now - STALE_SECONDS, now), FreshnessStatus.FRESH)

    def test_boundary_exactly_at_expired_threshold(self) -> None:
        now = self._now()
        self.assertEqual(freshness_of(now - EXPIRED_SECONDS, now), FreshnessStatus.STALE)


# ---------------------------------------------------------------------------
# ContextMeasurement / percent_used tests
# ---------------------------------------------------------------------------

class ContextMeasurementTests(unittest.TestCase):

    def _fresh_ts(self) -> float:
        return time.time() - 5  # 5 seconds old → fresh

    def test_percent_requires_occupancy_semantic(self) -> None:
        m = ContextMeasurement(
            semantic=ContextSemantic.LAST_REQUEST_INPUT,
            used=50000, limit=200000,
            model="gpt-6-astra", route="https://api.openai.com/v1",
            event_time=self._fresh_ts(),
        )
        self.assertIsNone(m.percent_used)

    def test_percent_unavailable_semantic_is_none(self) -> None:
        m = ContextMeasurement(semantic=ContextSemantic.UNAVAILABLE)
        self.assertIsNone(m.percent_used)

    def test_percent_requires_nonnegative_used(self) -> None:
        m = ContextMeasurement(
            semantic=ContextSemantic.OCCUPANCY,
            used=-1, limit=200000,
            model="m", route="https://r",
            event_time=self._fresh_ts(),
        )
        self.assertIsNone(m.percent_used)

    def test_percent_requires_positive_limit(self) -> None:
        for bad_limit in (0, -1, None):
            with self.subTest(limit=bad_limit):
                m = ContextMeasurement(
                    semantic=ContextSemantic.OCCUPANCY,
                    used=100, limit=bad_limit,
                    model="m", route="https://r",
                    event_time=self._fresh_ts(),
                )
                self.assertIsNone(m.percent_used)

    def test_percent_requires_model_and_route(self) -> None:
        for model, route in ((None, "https://r"), ("m", None), (None, None)):
            with self.subTest(model=model, route=route):
                m = ContextMeasurement(
                    semantic=ContextSemantic.OCCUPANCY,
                    used=50000, limit=200000,
                    model=model, route=route,
                    event_time=self._fresh_ts(),
                )
                self.assertIsNone(m.percent_used)

    def test_percent_suppressed_when_expired(self) -> None:
        m = ContextMeasurement(
            semantic=ContextSemantic.OCCUPANCY,
            used=50000, limit=200000,
            model="m", route="https://r",
            event_time=time.time() - EXPIRED_SECONDS - 60,
        )
        self.assertIsNone(m.percent_used)

    def test_percent_suppressed_when_unknown_timestamp(self) -> None:
        m = ContextMeasurement(
            semantic=ContextSemantic.OCCUPANCY,
            used=50000, limit=200000,
            model="m", route="https://r",
            event_time=None,
        )
        self.assertIsNone(m.percent_used)

    def test_percent_computed_correctly_for_valid_occupancy(self) -> None:
        m = ContextMeasurement(
            semantic=ContextSemantic.OCCUPANCY,
            used=100000, limit=200000,
            model="gpt-6-astra", route="https://api.openai.com/v1",
            event_time=self._fresh_ts(),
        )
        result = m.percent_used
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 50.0)

    def test_boolean_used_or_limit_is_rejected(self) -> None:
        """bool is a subclass of int; we must not treat True/False as 1/0."""
        for used, limit in ((True, 200000), (100000, True)):
            with self.subTest(used=used, limit=limit):
                m = ContextMeasurement(
                    semantic=ContextSemantic.OCCUPANCY,
                    used=used, limit=limit,
                    model="m", route="https://r",
                    event_time=self._fresh_ts(),
                )
                self.assertIsNone(m.percent_used)

    def test_unavailable_measurement_has_no_percent(self) -> None:
        m = ContextMeasurement()  # all defaults
        self.assertEqual(m.semantic, ContextSemantic.UNAVAILABLE)
        self.assertIsNone(m.percent_used)


# ---------------------------------------------------------------------------
# SessionRecord defaults
# ---------------------------------------------------------------------------

class SessionRecordTests(unittest.TestCase):

    def test_default_activity_is_unknown(self) -> None:
        s = SessionRecord(provider_id="p", session_id="s")
        self.assertEqual(s.activity, ActivityStatus.UNKNOWN)

    def test_default_context_is_unavailable(self) -> None:
        s = SessionRecord(provider_id="p", session_id="s")
        self.assertEqual(s.context.semantic, ContextSemantic.UNAVAILABLE)
        self.assertIsNone(s.context.used)
        self.assertIsNone(s.context.limit)

    def test_freshness_without_event_time_is_unknown(self) -> None:
        s = SessionRecord(provider_id="p", session_id="s")
        self.assertEqual(s.freshness, FreshnessStatus.UNKNOWN)

    def test_lifecycle_status_independent_of_context_freshness(self) -> None:
        """A known activity status does not imply fresh context data."""
        s = SessionRecord(
            provider_id="p", session_id="s",
            activity=ActivityStatus.BUSY,
            context=ContextMeasurement(
                semantic=ContextSemantic.UNAVAILABLE,
                event_time=None,
            ),
        )
        self.assertEqual(s.activity, ActivityStatus.BUSY)
        self.assertEqual(s.context.freshness, FreshnessStatus.UNKNOWN)


# ---------------------------------------------------------------------------
# ProviderRegistry pluggability contract
# ---------------------------------------------------------------------------

class ProviderRegistryTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = ProviderRegistry()

    def test_register_then_appears_in_adapters(self) -> None:
        """Core pluggability: register → visible."""
        adapter = _DummyAdapter("alpha")
        self.registry.register(adapter)
        ids = self.registry.provider_ids()
        self.assertIn("alpha", ids)

    def test_unregister_then_disappears(self) -> None:
        """Core pluggability: unregister → gone — without touching shell/UI code."""
        adapter = _DummyAdapter("beta")
        self.registry.register(adapter)
        self.registry.unregister("beta")
        self.assertNotIn("beta", self.registry.provider_ids())
        self.assertIsNone(self.registry.get("beta"))

    def test_unregister_nonexistent_is_silent(self) -> None:
        self.registry.unregister("nonexistent")  # must not raise

    def test_add_remove_does_not_affect_other_adapters(self) -> None:
        self.registry.register(_DummyAdapter("p1"))
        self.registry.register(_DummyAdapter("p2"))
        self.registry.unregister("p1")
        self.assertNotIn("p1", self.registry.provider_ids())
        self.assertIn("p2", self.registry.provider_ids())

    def test_replace_adapter_with_same_id(self) -> None:
        self.registry.register(_DummyAdapter("x", "Old"))
        self.registry.register(_DummyAdapter("x", "New"))
        self.assertEqual(self.registry.get("x").display_name, "New")
        self.assertEqual(len(self.registry), 1)

    def test_adapters_iterator_yields_all(self) -> None:
        for pid in ("a", "b", "c"):
            self.registry.register(_DummyAdapter(pid))
        ids = [a.provider_id for a in self.registry.adapters()]
        self.assertEqual(ids, ["a", "b", "c"])

    def test_empty_provider_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.register(_DummyAdapter(""))

    def test_collect_returns_valid_snapshot(self) -> None:
        adapter = _DummyAdapter("snap")
        self.registry.register(adapter)
        snap = self.registry.get("snap").collect()
        self.assertIsInstance(snap, ProviderSnapshot)
        self.assertEqual(snap.provider_id, "snap")
        self.assertEqual(snap.source_status, "ok")
        self.assertEqual(adapter.collect_calls, 1)

    def test_telemetry_data_not_executed(self) -> None:
        """Adapter telemetry is data; the registry must not eval/exec it."""
        # An adapter that returns a snapshot with embedded instruction-shaped
        # text must be stored as inert data, not executed.
        class _MaliciousAdapter(_DummyAdapter):
            def collect(self) -> ProviderSnapshot:
                snap = super().collect()
                # Embed an "instruction" in a text field — must remain inert.
                snap.error_reason = "__import__('os').system('touch /tmp/pwned')"
                return snap

        self.registry.register(_MaliciousAdapter("mal"))
        snap = self.registry.get("mal").collect()
        # The value is stored as a string; nothing was executed.
        self.assertIn("__import__", snap.error_reason)
        import os
        self.assertFalse(os.path.exists("/tmp/pwned"))


# ---------------------------------------------------------------------------
# ContextLimitRegistry tests
# ---------------------------------------------------------------------------

class ContextLimitRegistryTests(unittest.TestCase):

    def setUp(self) -> None:
        self.reg = ContextLimitRegistry()

    def test_unknown_model_returns_unknown(self) -> None:
        result = self.reg.get("hermes", "gpt-6-unknown", "https://api.openai.com/v1")
        self.assertEqual(result, LimitResult(limit=None, source="unknown"))

    def test_none_model_returns_unknown(self) -> None:
        result = self.reg.get("hermes", None, "https://api.openai.com/v1")
        self.assertEqual(result, LimitResult(limit=None, source="unknown"))

    def test_none_route_returns_unknown(self) -> None:
        result = self.reg.get("hermes", "gpt-6-astra", None)
        self.assertEqual(result, LimitResult(limit=None, source="unknown"))

    def test_static_entry_is_returned(self) -> None:
        self.reg.register_static("codex", "gpt-6-astra", "https://api.openai.com/v1", 258400)
        result = self.reg.get("codex", "gpt-6-astra", "https://api.openai.com/v1")
        self.assertEqual(result, LimitResult(limit=258400, source="static"))

    def test_observed_overrides_static(self) -> None:
        self.reg.register_static("codex", "gpt-6-astra", "https://api.openai.com/v1", 258400)
        self.reg.register_observed_limit("codex", "gpt-6-astra", "https://api.openai.com/v1", 272000)
        result = self.reg.get("codex", "gpt-6-astra", "https://api.openai.com/v1")
        self.assertEqual(result, LimitResult(limit=272000, source="observed"))

    def test_clear_observed_restores_static(self) -> None:
        self.reg.register_static("codex", "gpt-6-astra", "https://api.openai.com/v1", 258400)
        self.reg.register_observed_limit("codex", "gpt-6-astra", "https://api.openai.com/v1", 272000)
        self.reg.clear_observed()
        result = self.reg.get("codex", "gpt-6-astra", "https://api.openai.com/v1")
        self.assertEqual(result, LimitResult(limit=258400, source="static"))

    def test_route_normalization_trailing_slash(self) -> None:
        self.reg.register_static("p", "m", "https://api.example.com/v1/", 100000)
        result = self.reg.get("p", "m", "https://api.example.com/v1")
        self.assertEqual(result.limit, 100000)

    def test_different_routes_do_not_merge(self) -> None:
        self.reg.register_static("p", "m", "https://api.openai.com/v1", 258400)
        result = self.reg.get("p", "m", "https://api.azure.com/v1")
        self.assertEqual(result, LimitResult(limit=None, source="unknown"))

    def test_different_providers_do_not_cross(self) -> None:
        self.reg.register_static("provider-a", "model-x", "https://api.example.com", 100000)
        result = self.reg.get("provider-b", "model-x", "https://api.example.com")
        self.assertEqual(result, LimitResult(limit=None, source="unknown"))

    def test_zero_limit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.reg.register_static("p", "m", "https://r", 0)

    def test_negative_limit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.reg.register_static("p", "m", "https://r", -1)

    def test_boolean_limit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.reg.register_static("p", "m", "https://r", True)

    def test_empty_route_rejected_for_static(self) -> None:
        with self.assertRaises(ValueError):
            self.reg.register_static("p", "m", "", 100000)

    def test_hermes_known_route_example(self) -> None:
        """Hermes uses codex-routed models at 272,000 tokens (ACC-02 evidence)."""
        self.reg.register_static(
            "hermes", "gpt-6-luna", "https://gateway.hermes.local/v1", 272000
        )
        result = self.reg.get("hermes", "gpt-6-luna", "https://gateway.hermes.local/v1")
        self.assertEqual(result.limit, 272000)

    def test_models_dev_catalogue_match_is_not_used(self) -> None:
        """The 3.86x trap: models.dev says 1,050,000; observed is 272,000.

        The registry must return unknown for an unregistered (model, route)
        pair — it must never fall back to a public catalogue lookup.
        """
        # Only register the correct observed limit.
        self.reg.register_observed_limit(
            "hermes", "gpt-6-luna", "https://gateway.hermes.local/v1", 272000
        )
        # A lookup with the wrong route (e.g. a models.dev entry keyed by
        # model name alone) must return unknown, not 1,050,000.
        result = self.reg.get("hermes", "gpt-6-luna", "https://models.dev/api")
        self.assertEqual(result, LimitResult(limit=None, source="unknown"))


# ---------------------------------------------------------------------------
# Snapshot model defaults
# ---------------------------------------------------------------------------

class ProviderSnapshotTests(unittest.TestCase):

    def test_default_source_status_is_unknown(self) -> None:
        snap = ProviderSnapshot(provider_id="p", display_name="P")
        self.assertEqual(snap.source_status, "unknown")

    def test_empty_sessions_is_not_connected(self) -> None:
        snap = ProviderSnapshot(provider_id="p", display_name="P")
        self.assertEqual(snap.sessions, [])
        self.assertFalse(snap.truncated)

    def test_error_fields_default_to_none(self) -> None:
        snap = ProviderSnapshot(provider_id="p", display_name="P")
        self.assertIsNone(snap.error_code)
        self.assertIsNone(snap.error_reason)


if __name__ == "__main__":
    unittest.main()
