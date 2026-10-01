"""Demo adapter (demo mode only).

Registered only when the server starts with --demo / ACC_DEMO=1. Every
value is an explicitly labeled fixture — the API reports "mode": "demo"
and the UI shows a persistent SAMPLE DATA banner. Demo fixtures are never
used silently: live mode with no real adapters shows an honest
"no providers connected" state instead.

The three demo providers mirror the ACC-05 mockup scenarios: healthy
sessions, a stale session, an unknown model limit (percent unavailable),
and a provider-level error demonstrating isolation.
"""
from __future__ import annotations

from datetime import timedelta

from .adapters import Adapter, AdapterError
from .model import AdapterReading, ToolCall, utcnow

_FIXTURE_SOURCE = "demo fixture — not live telemetry"


def _tool(tool: str, outcome: str, note: str, age_sec: int) -> ToolCall:
    return ToolCall(tool=tool, outcome=outcome, note=note,
                    at=utcnow() - timedelta(seconds=age_sec))


class DemoAdapter:
    """One demo provider. `scenario` picks which fixture set to serve."""

    def __init__(self, provider: str, scenario: str) -> None:
        self.name = provider
        self._scenario = scenario

    def read(self) -> list[AdapterReading]:
        now = utcnow()
        if self._scenario == "hermes":
            return [
                AdapterReading(
                    provider="Hermes", session_id="hermes-main",
                    model="hermes-2-pro", activity="working",
                    context_used=42150, source=_FIXTURE_SOURCE,
                    observed_at=now - timedelta(seconds=12),
                    tools=(_tool("read_file", "ok", "", 38),
                           _tool("web_search", "ok", "", 21),
                           _tool("exec", "error", "timeout after 30s", 9)),
                ),
                AdapterReading(
                    provider="Hermes", session_id="hermes-bg-01",
                    model="hermes-2-pro", activity="idle",
                    context_used=8400, source=_FIXTURE_SOURCE,
                    observed_at=now - timedelta(seconds=45),
                    tools=(_tool("read_file", "ok", "", 52),),
                ),
            ]
        if self._scenario == "claude":
            return [
                AdapterReading(
                    provider="Claude Code", session_id="cc-parent",
                    model="claude-opus-4-6", activity="working",
                    context_used=96000, source=_FIXTURE_SOURCE,
                    observed_at=now - timedelta(seconds=243),  # stale (>60s)
                    tools=(_tool("edit_file", "ok", "", 230),
                           _tool("exec", "ok", "", 196)),
                ),
                AdapterReading(
                    provider="Claude Code", session_id="cc-child-3",
                    model="claude-opus-4-6-experimental",  # not in limit registry
                    activity="idle", context_used=12300,
                    source=_FIXTURE_SOURCE,
                    observed_at=now - timedelta(seconds=96),
                    tools=(_tool("web_search", "ok", "", 88),),
                ),
            ]
        if self._scenario == "codex-error":
            raise AdapterError("sqlite database locked — could not read "
                               "sessions (demo)")
        raise AdapterError(f"unknown demo scenario {self._scenario!r}")


DEMO_LIMITS: tuple[tuple[str, str, int], ...] = (
    ("Hermes", "hermes-2-pro", 200_000),
    ("Claude Code", "claude-opus-4-6", 200_000),
    # claude-opus-4-6-experimental deliberately absent: demonstrates the
    # unknown-limit unavailable state.
)


def register_demo(registry, limits) -> None:
    """Register the three demo providers and their fixture limits."""
    from .registry import ProviderRegistry, ModelLimitRegistry  # local import
    assert isinstance(registry, ProviderRegistry)
    assert isinstance(limits, ModelLimitRegistry)
    registry.register("Hermes", DemoAdapter("Hermes", "hermes"))
    registry.register("Claude Code", DemoAdapter("Claude Code", "claude"))
    registry.register("Codex", DemoAdapter("Codex", "codex-error"))
    for provider, model_id, limit in DEMO_LIMITS:
        limits.set_limit(provider, model_id, limit)
