"""Normalized telemetry model (ACC-08).

Adapters return AdapterReading: what the provider reported, with the model
identifier exactly as the provider reports it. The server resolves the
context limit through the ModelLimitRegistry and computes percent_used —
no other module may define where a limit comes from.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ToolCall:
    """One observed tool invocation. Name, outcome and error note only —
    never prompt text or conversation content."""

    tool: str
    outcome: str  # "ok" | "error"
    note: str = ""
    at: datetime | None = None  # when the call completed, if the adapter knows


@dataclass(frozen=True)
class AdapterReading:
    """One session as reported by an adapter. context_used is a measured
    value or None; the limit is resolved later by the server."""

    provider: str
    session_id: str
    model: str  # raw model identifier, exactly as the provider reports it
    activity: str  # "working" | "idle" | "error" | "unknown"
    context_used: int | None
    source: str  # human-readable measurement source, e.g. "measured via Hermes local API"
    observed_at: datetime
    unavailable_reason: str | None = None  # why a metric is unavailable, if it is
    error: str | None = None  # provider/session-level error, if any
    tools: tuple = field(default_factory=tuple)  # tuple[ToolCall, ...]


def reading_to_view(reading: AdapterReading, context_limit: int | None,
                    now: datetime, stale_after_sec: int) -> dict:
    """Enrich a raw reading into the API view dict. Percent is computed only
    from a measured used/limit pair for the same model; otherwise it is null
    with an explicit reason. Freshness is derived from observed_at."""
    used = reading.context_used
    percent = None
    reason = reading.unavailable_reason
    if used is not None and context_limit:
        percent = round(used / context_limit * 100)
    elif reason is None:
        if used is None:
            reason = "context usage not reported by provider"
        else:
            reason = f"model id {reading.model!r} not in limit registry"
    age_sec = max(0.0, (now - reading.observed_at).total_seconds())
    freshness = "stale" if age_sec > stale_after_sec else "fresh"
    return {
        "provider": reading.provider,
        "session_id": reading.session_id,
        "model": reading.model,
        "activity": reading.activity,
        "context_used": used,
        "context_limit": context_limit,
        "percent_used": percent,
        "unavailable_reason": reason,
        "source": reading.source,
        "observed_at": reading.observed_at.isoformat(),
        "age_sec": round(age_sec),
        "freshness": freshness,
        "error": reading.error,
        "tools": [
            {
                "tool": t.tool,
                "outcome": t.outcome,
                "note": t.note,
                "at": t.at.isoformat() if t.at else None,
            }
            for t in reading.tools
        ],
    }
