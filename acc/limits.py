"""Model context-limit registry.

ACC-08 owns the denominator.  No other module may define where a model's
context limit comes from.

Keying rule (architecture §"Context fields"):
    (provider_id, exact_model_string, normalized_route)

Route normalization strips only trailing slashes and whitespace.  Different
schemes, hosts, ports, or paths are distinct routes and must not be merged.
An unknown route (None) cannot match any static entry.

A provider-reported same-measurement limit may be registered directly via
``register_observed_limit``; it takes precedence over static entries.

An unrecognised key yields LimitResult(limit=None, source="unknown") — never
a default, never a guess from a public model catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LimitResult:
    """Result returned by ``ContextLimitRegistry.get``."""
    limit: Optional[int]  # context window size in tokens; None if unknown
    source: str           # "static", "observed", or "unknown"


def _normalize_route(route: Optional[str]) -> Optional[str]:
    """Strip only trailing slashes and whitespace; preserve everything else."""
    if route is None:
        return None
    normalized = route.rstrip("/ \t\n\r")
    return normalized if normalized else None


class ContextLimitRegistry:
    """Single source of truth for model context-window sizes.

    Thread-safety: this class is not thread-safe.  The collector runs each
    adapter in a child process, so the registry is read (never written) at
    poll time; writes happen only during configuration loading in the parent.

    Static entries are pre-loaded from configuration.  Observed entries come
    from provider telemetry (e.g. Codex ``model_context_window``) and
    override static entries for the same key.
    """

    def __init__(self) -> None:
        # (provider_id, model, normalized_route) -> limit_tokens
        self._static: dict[tuple[str, str, str], int] = {}
        # Same key structure; populated at poll time from provider telemetry.
        self._observed: dict[tuple[str, str, str], int] = {}

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def register_static(
        self,
        provider_id: str,
        model: str,
        route: str,
        limit: int,
    ) -> None:
        """Add or replace a static (configuration-time) limit entry.

        Parameters
        ----------
        provider_id:
            Registry key of the provider (e.g. ``"hermes"``).
        model:
            Exact model string as reported by the provider.
        route:
            Base URL for this route.  Must not be None; unknown routes
            cannot have a static limit because the key would be ambiguous.
        limit:
            Context window size in tokens.  Must be a positive integer.
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit!r}")
        norm = _normalize_route(route)
        if norm is None:
            raise ValueError("route must be a non-empty string for a static entry")
        self._static[(provider_id, model, norm)] = limit

    def register_observed_limit(
        self,
        provider_id: str,
        model: str,
        route: str,
        limit: int,
    ) -> None:
        """Record a limit reported by the provider during a polling cycle.

        Observed limits override static entries for the same key.  They are
        cleared on each reload of the registry (i.e. application restart).
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit!r}")
        norm = _normalize_route(route)
        if norm is None:
            raise ValueError("route must be a non-empty string for an observed limit")
        self._observed[(provider_id, model, norm)] = limit

    def clear_observed(self) -> None:
        """Discard all provider-reported limits (e.g. on a polling error)."""
        self._observed.clear()

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get(
        self,
        provider_id: str,
        model: Optional[str],
        route: Optional[str],
    ) -> LimitResult:
        """Return the context limit for (provider_id, model, route).

        Returns LimitResult(limit=None, source="unknown") for any unrecognised
        combination, including when model or route is None.
        """
        if model is None or route is None:
            return LimitResult(limit=None, source="unknown")
        norm = _normalize_route(route)
        if norm is None:
            return LimitResult(limit=None, source="unknown")
        key = (provider_id, model, norm)
        if key in self._observed:
            return LimitResult(limit=self._observed[key], source="observed")
        if key in self._static:
            return LimitResult(limit=self._static[key], source="static")
        return LimitResult(limit=None, source="unknown")

    def __len__(self) -> int:
        return len(self._static) + len(self._observed)


# Module-level singleton used by the collector and server.
# Tests should construct their own instance to avoid cross-test pollution.
_default_registry: Optional[ContextLimitRegistry] = None


def get_default_registry() -> ContextLimitRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ContextLimitRegistry()
    return _default_registry


def reset_default_registry() -> None:
    """Replace the module singleton — for use in tests only."""
    global _default_registry
    _default_registry = ContextLimitRegistry()
