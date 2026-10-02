"""Provider registry and model context-limit registry (ACC-08).

The provider registry is the only place that names providers. Shell and UI
code resolve providers exclusively through it, so adding or removing a
provider is a registry entry plus one adapter module.

The limit registry is the single source of truth mapping a
provider-reported model identifier to its context limit. Unknown models
yield None — never a default, never a guess.
"""
from __future__ import annotations

from .adapters import Adapter, AdapterError  # noqa: F401  (re-exported for adapters)


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, Adapter] = {}

    def register(self, name: str, adapter: Adapter) -> None:
        if not name or not name.strip():
            raise ValueError("provider name must be a non-empty string")
        self._adapters[name] = adapter

    def unregister(self, name: str) -> None:
        self._adapters.pop(name, None)

    def get(self, name: str) -> Adapter | None:
        return self._adapters.get(name)

    def names(self) -> list[str]:
        return sorted(self._adapters.keys())

    def __len__(self) -> int:
        return len(self._adapters)


class ModelLimitRegistry:
    """Maps (provider, provider-reported model id) -> context limit tokens."""

    def __init__(self) -> None:
        self._limits: dict[tuple[str, str], int] = {}

    def set_limit(self, provider: str, model_id: str, limit: int) -> None:
        if limit <= 0:
            raise ValueError("context limit must be positive")
        self._limits[(provider, model_id)] = limit

    def get_limit(self, provider: str, model_id: str) -> int | None:
        """None means unknown: the caller must show unavailable, not guess."""
        return self._limits.get((provider, model_id))
