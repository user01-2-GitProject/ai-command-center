"""Normalized telemetry models shared across all provider adapters.

Every field that can be absent or unverified is typed as Optional and
defaults to None. Adapters must never substitute a plausible guess for
a field they cannot read; use the explicit sentinel values below instead.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Sentinel / enum types
# ---------------------------------------------------------------------------

class ActivityStatus(str, Enum):
    """Lifecycle state of a session as reported by the provider.

    UNKNOWN means the adapter could not determine state — not that the
    session is necessarily idle. Callers must not treat UNKNOWN as IDLE.
    """
    UNKNOWN = "unknown"
    IDLE = "idle"
    BUSY = "busy"
    ENDED = "ended"


class ContextSemantic(str, Enum):
    """What a context numerator actually measures."""
    OCCUPANCY = "occupancy"            # tokens currently in the context window
    LAST_REQUEST_INPUT = "last_request_input"  # most recent API call's input tokens
    UNAVAILABLE = "unavailable"        # no supported measurement exists


class FreshnessStatus(str, Enum):
    """Age classification of a single measurement."""
    FRESH = "fresh"          # observed within STALE_SECONDS
    STALE = "stale"          # observed within EXPIRED_SECONDS
    EXPIRED = "expired"      # older than EXPIRED_SECONDS or no timestamp
    UNKNOWN = "unknown"      # timestamp missing, None, or unparseable


# Freshness thresholds (seconds). Architecture §"Shared model and limits".
STALE_SECONDS: int = 30
EXPIRED_SECONDS: int = 300  # 5 minutes


def freshness_of(event_time: Optional[float], now: Optional[float] = None) -> FreshnessStatus:
    """Classify a measurement by its age.

    Parameters
    ----------
    event_time:
        Unix timestamp of the measurement, or None if unknown.
    now:
        Current time; defaults to time.time(). Accepted as a parameter
        so tests can pass a fixed reference without monkeypatching.
    """
    if event_time is None:
        return FreshnessStatus.UNKNOWN
    try:
        age = (now if now is not None else time.time()) - float(event_time)
    except (TypeError, ValueError, OverflowError):
        return FreshnessStatus.UNKNOWN
    if age < 0:
        # Clock skew or a future timestamp — treat as unknown rather than fresh.
        return FreshnessStatus.UNKNOWN
    if age <= STALE_SECONDS:
        return FreshnessStatus.FRESH
    if age <= EXPIRED_SECONDS:
        return FreshnessStatus.STALE
    return FreshnessStatus.EXPIRED


# ---------------------------------------------------------------------------
# Context measurement
# ---------------------------------------------------------------------------

@dataclass
class ContextMeasurement:
    """A single context reading from a provider.

    Rules (from architecture §"Context fields"):
    - ``semantic`` determines how ``used`` may be displayed and whether a
      percentage is legal.
    - A percentage requires: nonneg integer ``used``, positive integer
      ``limit``, identical ``model`` and ``route`` on both sides,
      ``semantic == OCCUPANCY``, and freshness FRESH or STALE.
    - ``last_request_input`` may be shown as a labelled historical figure
      but must never feed a percentage.
    - ``unavailable`` means the field is absent; ``used`` and ``limit``
      should be None.
    """
    semantic: ContextSemantic = ContextSemantic.UNAVAILABLE
    used: Optional[int] = None        # tokens (numerator); None if unavailable
    limit: Optional[int] = None       # tokens (denominator); None if unknown
    model: Optional[str] = None       # exact model string this limit applies to
    route: Optional[str] = None       # normalized base URL; None if unknown
    event_time: Optional[float] = None  # Unix timestamp of the measurement
    unavailable_reason: Optional[str] = None  # human-readable explanation

    @property
    def freshness(self) -> FreshnessStatus:
        return freshness_of(self.event_time)

    @property
    def percent_used(self) -> Optional[float]:
        """Return occupancy percentage, or None if it cannot be computed.

        None is returned (never 0, never a guess) whenever:
        - semantic is not OCCUPANCY
        - used or limit is None
        - used is negative
        - limit is not a positive integer
        - model or route is None (denominator identity unverifiable)
        - freshness is EXPIRED or UNKNOWN
        """
        if self.semantic is not ContextSemantic.OCCUPANCY:
            return None
        if self.used is None or self.limit is None:
            return None
        if not isinstance(self.used, int) or isinstance(self.used, bool):
            return None
        if not isinstance(self.limit, int) or isinstance(self.limit, bool):
            return None
        if self.used < 0 or self.limit <= 0:
            return None
        if self.model is None or self.route is None:
            return None
        if self.freshness in (FreshnessStatus.EXPIRED, FreshnessStatus.UNKNOWN):
            return None
        return self.used / self.limit * 100.0


# ---------------------------------------------------------------------------
# Session record
# ---------------------------------------------------------------------------

@dataclass
class SessionRecord:
    """One provider session as seen by a read-only adapter.

    Fields that an adapter cannot determine must remain None.  The caller
    must not infer activity from a populated database row alone; the
    ``activity_provenance`` field exists precisely to record what evidence
    the adapter actually had.
    """
    # Identity
    provider_id: str = ""         # registry key of the provider
    session_id: str = ""          # opaque, provider-specific
    parent_session_id: Optional[str] = None

    # Observed metadata
    model: Optional[str] = None   # exact string, never inferred
    source: Optional[str] = None  # e.g. "cli", "telegram", "subagent"

    # Timing
    event_time: Optional[float] = None  # Unix ts of most recent observed event
    started_at: Optional[float] = None

    # Activity
    activity: ActivityStatus = ActivityStatus.UNKNOWN
    activity_provenance: Optional[str] = None  # e.g. "registration.status"

    # Context
    context: ContextMeasurement = field(default_factory=ContextMeasurement)

    # Optional pressure/compaction counters (Hermes-specific but typed here
    # so ACC-12 can render them generically without importing Hermes internals)
    messages_in_window: Optional[int] = None   # live-window count; NOT a total
    messages_compacted: Optional[int] = None   # cumulative folded count
    compaction_count: Optional[int] = None     # number of compaction events

    @property
    def freshness(self) -> FreshnessStatus:
        return freshness_of(self.event_time)


# ---------------------------------------------------------------------------
# Provider snapshot
# ---------------------------------------------------------------------------

@dataclass
class ProviderSnapshot:
    """Everything an adapter returned for one polling cycle.

    The collector holds one snapshot per configured provider in memory;
    a restart clears all snapshots.
    """
    provider_id: str = ""
    display_name: str = ""

    # Source connectivity
    source_status: str = "unknown"   # "ok", "offline", "error", "unknown"
    source_version: Optional[str] = None
    observation_time: Optional[float] = None  # Unix ts of this polling cycle

    # Error surface — redacted code/reason only; never raw tracebacks
    error_code: Optional[str] = None
    error_reason: Optional[str] = None

    sessions: list[SessionRecord] = field(default_factory=list)
    truncated: bool = False   # True if adapter hit its session/output budget
