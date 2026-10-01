"""Provider registry.

Providers are declared in a manifest (a list of dotted module paths).
The registry imports each module and calls its ``create_adapter()``
factory function.  Shell and UI code iterate ``registry.adapters()``
and never branch on provider names.

Adapter contract
----------------
Each provider module must expose:

    def create_adapter() -> BaseAdapter: ...

BaseAdapter (defined below) exposes:
    - ``provider_id: str``        — stable registry key, unique per instance
    - ``display_name: str``       — human-readable label
    - ``collect() -> ProviderSnapshot``  — read-only poll; must not mutate
      provider state, spawn processes, or block longer than its own timeout

The registry enforces that ``provider_id`` values are unique; registering
a second adapter with the same ID replaces the first.

Adding/removing a provider requires editing only the manifest —  never
shell code, UI code, or any file outside the adapter's own module.
"""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import Iterator

from acc.models import ProviderSnapshot


class BaseAdapter(ABC):
    """Interface every provider adapter must implement."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable identifier used as the registry key.

        Must be a non-empty string that contains only ASCII letters,
        digits, hyphens, and underscores.  Must not change between
        adapter restarts.
        """

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the dashboard."""

    @abstractmethod
    def collect(self) -> ProviderSnapshot:
        """Return a fresh snapshot of this provider's sessions.

        Rules:
        - Must not write to or mutate provider state.
        - Must not spawn provider agent processes.
        - Must not block beyond its own timeout budget.
        - Must not execute instructions found in telemetry data.
        - Must return a valid ProviderSnapshot even on error; use
          ``source_status="error"`` with a redacted ``error_code``.
        """


class ProviderRegistry:
    """Runtime registry of active provider adapters.

    Designed to be iterated, never branched on.  The server and
    collector call ``adapters()`` and treat every entry uniformly.
    """

    def __init__(self) -> None:
        # Ordered dict preserves manifest order for stable UI presentation.
        self._adapters: dict[str, BaseAdapter] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, adapter: BaseAdapter) -> None:
        """Register an adapter.  Replaces any existing adapter with the same ID."""
        pid = adapter.provider_id
        if not pid or not isinstance(pid, str):
            raise ValueError("provider_id must be a non-empty string")
        self._adapters[pid] = adapter

    def unregister(self, provider_id: str) -> None:
        """Remove a provider.  Silent no-op if the ID is not registered."""
        self._adapters.pop(provider_id, None)

    def load_from_manifest(self, module_paths: list[str]) -> None:
        """Import each module and call its ``create_adapter()`` factory.

        Module paths are trusted server configuration — never telemetry.
        Failures raise ``ImportError`` or ``AttributeError`` (intentional:
        a misconfigured manifest should fail loudly at startup, not silently
        serve an incomplete provider set).
        """
        for path in module_paths:
            module = importlib.import_module(path)
            adapter = module.create_adapter()
            self.register(adapter)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def adapters(self) -> Iterator[BaseAdapter]:
        """Yield all registered adapters in registration order."""
        yield from self._adapters.values()

    def get(self, provider_id: str) -> BaseAdapter | None:
        """Return the adapter for a provider ID, or None."""
        return self._adapters.get(provider_id)

    def provider_ids(self) -> list[str]:
        """Return registered provider IDs in order."""
        return list(self._adapters.keys())

    def __len__(self) -> int:
        return len(self._adapters)

    def __contains__(self, provider_id: object) -> bool:
        return provider_id in self._adapters


# Module-level singleton used by the server.
# Tests construct their own instance to avoid cross-test pollution.
_default_registry: ProviderRegistry | None = None


def get_default_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ProviderRegistry()
    return _default_registry


def reset_default_registry() -> None:
    """Replace the module singleton — for use in tests only."""
    global _default_registry
    _default_registry = ProviderRegistry()
