"""Adapter interface (ACC-08).

A provider adapter is a read-only module implementing the Adapter protocol.
Adapters return sanitized metadata only: session identity, activity, model,
measured context values, tool names/outcomes. Never prompt text,
conversation content, or secrets. Telemetry is untrusted data — the server
serializes it with json (which escapes HTML) and the UI inserts it as text,
never as HTML.
"""
from __future__ import annotations

from typing import Protocol

from .model import AdapterReading


class AdapterError(Exception):
    """Raised when a read fails: source missing/unreachable, timeout, or
    malformed data. The message is shown to the user as the provider's
    error state, so keep it human-readable and free of secrets."""


class Adapter(Protocol):
    """Read-only provider adapter. Must not mutate provider state, dispatch
    work, send messages, or read prompt/conversation content or secrets."""

    name: str

    def read(self) -> list[AdapterReading]:
        """Return current session readings. Raise AdapterError on failure."""
        ...
