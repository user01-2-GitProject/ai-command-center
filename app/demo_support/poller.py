"""Polling loop (ACC-08/ACC-12).

Calls every registered adapter on a fixed interval, concurrently, with a
per-adapter timeout. One adapter hanging or raising cannot delay or erase
the others. Polls never overlap: a slow poll is skipped, not stacked.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from .adapters import AdapterError
from .model import AdapterReading, reading_to_view, utcnow
from .registry import ModelLimitRegistry, ProviderRegistry


@dataclass
class ProviderPoll:
    provider: str
    ok: bool
    error: str | None
    readings: list = field(default_factory=list)  # list[AdapterReading]
    polled_at: datetime = field(default_factory=utcnow)


class Poller:
    def __init__(
        self,
        registry: ProviderRegistry,
        limits: ModelLimitRegistry,
        interval_sec: int = 15,
        timeout_sec: int = 10,
        stale_after_sec: int = 60,
    ) -> None:
        self.registry = registry
        self.limits = limits
        self.interval_sec = interval_sec
        self.timeout_sec = timeout_sec
        self.stale_after_sec = stale_after_sec
        self._cache: dict[str, ProviderPoll] = {}
        self._lock = threading.Lock()
        self._polling = False

    def _read_one(self, name: str) -> ProviderPoll:
        adapter = self.registry.get(name)
        if adapter is None:  # unregistered mid-poll; drop it
            return ProviderPoll(provider=name, ok=False,
                                error="provider unregistered during poll",
                                polled_at=utcnow())
        try:
            readings = adapter.read()
            if not isinstance(readings, list):
                raise AdapterError("adapter returned malformed data (not a list)")
            return ProviderPoll(provider=name, ok=True, error=None,
                                readings=readings, polled_at=utcnow())
        except AdapterError as exc:
            return ProviderPoll(provider=name, ok=False, error=str(exc),
                                polled_at=utcnow())
        except Exception as exc:  # never let one adapter kill the poll
            return ProviderPoll(provider=name, ok=False,
                                error=f"adapter failed: {type(exc).__name__}",
                                polled_at=utcnow())

    def poll_once(self) -> None:
        """Run one poll cycle. Skips if the previous cycle is still running."""
        with self._lock:
            if self._polling:
                return
            self._polling = True
        try:
            names = self.registry.names()
            if not names:
                return
            with ThreadPoolExecutor(max_workers=len(names)) as pool:
                futures = {pool.submit(self._read_one, n): n for n in names}
                for fut, name in futures.items():
                    try:
                        self._cache[name] = fut.result(timeout=self.timeout_sec)
                    except Exception:
                        self._cache[name] = ProviderPoll(
                            provider=name, ok=False,
                            error=f"adapter timed out after {self.timeout_sec}s",
                            polled_at=utcnow())
            # drop providers that were unregistered while polling
            for name in list(self._cache):
                if name not in names:
                    del self._cache[name]
        finally:
            with self._lock:
                self._polling = False

    def payload(self, mode: str) -> dict:
        """The /api/sessions body. Freshness and percent are computed here,
        at serve time, from each reading's observed_at and the limit registry."""
        now = utcnow()
        providers = []
        for name in self.registry.names():
            poll = self._cache.get(name)
            if poll is None:
                providers.append({"provider": name, "ok": False,
                                  "error": "no poll completed yet",
                                  "sessions": []})
                continue
            providers.append({
                "provider": name,
                "ok": poll.ok,
                "error": poll.error,
                "polled_at": poll.polled_at.isoformat(),
                "sessions": [
                    reading_to_view(
                        r,
                        self.limits.get_limit(r.provider, r.model),
                        now,
                        self.stale_after_sec,
                    )
                    for r in poll.readings
                ],
            })
        return {
            "mode": mode,
            "generated_at": now.isoformat(),
            "stale_after_sec": self.stale_after_sec,
            "poll_interval_sec": self.interval_sec,
            "providers": providers,
        }
