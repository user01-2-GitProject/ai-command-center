"""Hermes read-only adapter.

Two sources only (column allowlist per docs/discovery/hermes.md):
  A. ~/.hermes/gateway.sock         verbs: identify, status (read-only)
  B. ~/.hermes/state.db             tables: sessions, session_model_usage (mode=ro)
  C. ~/.hermes/context_length_cache.yaml   observed limit cache (optional)

Explicitly excluded:
  - .env, auth.json, credentials/ — never opened.
  - messages table (token_count NULL for all rows; contains conversation text).
  - system_prompts table — prompt content.
  - sessions.title, .display_name, .cwd, .last_activity_description — user text.
  - runtime/active_sessions.json — reads as empty while agents run; unreliable.
  - request_dump_*.json — contain full request payloads (prompt content).
  - The seven mutating gateway verbs — never sent.
  - immutable=1 — silently skips WAL writes and produces stale reads; never used.

Context occupancy is UNAVAILABLE: messages.token_count is NULL for all rows;
the control socket has no context verb; the tui_gateway RPC reads a live in-memory
agent. A read-only observer cannot reach occupancy data. See docs/discovery/hermes.md.

Activity state for open sessions (ended_at IS NULL) is UNKNOWN: the adapter can
confirm a session ended but cannot distinguish idle from busy without the socket
context verb. The provenance field records the evidence actually used.
"""

from __future__ import annotations

import json
import re
import socket as _socket
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from acc.limits import ContextLimitRegistry
from acc.models import (
    ActivityStatus,
    ContextMeasurement,
    ContextSemantic,
    ProviderSnapshot,
    SessionRecord,
)
from acc.registry import BaseAdapter

PROVIDER_ID = "hermes"
DISPLAY_NAME = "Hermes"

_SOCKET_TIMEOUT: float = 2.0

# Stable string; tests may assert on it.
_CONTEXT_UNAVAILABLE_REASON: str = (
    "Hermes context occupancy is not reachable read-only: "
    "messages.token_count is NULL for all rows; "
    "the control socket has no context verb; "
    "the tui_gateway RPC reads a live in-memory agent. "
    "See docs/discovery/hermes.md."
)

# Column allowlist — never expand without a discovery justification.
_SESSION_COLS: Tuple[str, ...] = (
    "id", "source", "session_key", "parent_session_id",
    "model", "billing_provider", "billing_base_url", "billing_mode",
    "started_at", "ended_at", "last_activity_at",
    "message_count",
)
_SESSION_SQL = (
    f"SELECT {', '.join(_SESSION_COLS)} "
    "FROM sessions ORDER BY last_activity_at DESC"
)

# Compaction count per session via session_model_usage.
_COMPACTION_SQL = (
    "SELECT session_id, COUNT(*) AS compaction_count "
    "FROM session_model_usage WHERE task = 'compression' GROUP BY session_id"
)


# ---------------------------------------------------------------------------
# Gateway socket helper
# ---------------------------------------------------------------------------

def _ask_gateway(sock_path: str, verb: str, timeout: float = _SOCKET_TIMEOUT) -> dict:
    """Send one read-only verb to the Hermes control socket; return the response dict.

    Wire contract (from gateway/control_socket.py): one JSON line in, one line
    out, server closes.  Only ``identify`` and ``status`` are sent — both are
    read-only.  The seven mutating verbs are never used.

    Raises OSError on connection failure, json.JSONDecodeError on bad response.
    """
    payload = json.dumps({"verb": verb, "id": 1, "protocol": 1}) + "\n"
    s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock_path)
        s.sendall(payload.encode("utf-8"))
        buf = b""
        while True:
            try:
                chunk = s.recv(4096)
            except _socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8").strip())
    finally:
        try:
            s.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Limit cache parser
# ---------------------------------------------------------------------------

_LIMIT_LINE = re.compile(r"^(.+@\S+):\s*(\d+)\s*$")


def _parse_limit_cache(text: str) -> Dict[Tuple[str, str], int]:
    """Parse context_length_cache.yaml into ``{(model, base_url): limit_tokens}``.

    Line format inside the ``context_lengths`` mapping::

        model@base_url: integer

    Examples from the live cache::

        gpt-6-luna@https://chatgpt.com/backend-api/codex: 272000
        gemma4:26b@http://127.0.0.1:11434/v1: 262144

    Models do not contain ``@``; splitting on the first ``@`` separates model
    from base_url.  Route normalization (trailing slashes) is delegated to
    ``ContextLimitRegistry`` on registration.

    Malformed lines are skipped silently.
    """
    result: Dict[Tuple[str, str], int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        m = _LIMIT_LINE.match(line)
        if not m:
            continue
        full_key, limit_str = m.group(1), m.group(2)
        at_idx = full_key.find("@")
        if at_idx <= 0:
            continue
        model_str = full_key[:at_idx]
        base_url = full_key[at_idx + 1:]
        if not model_str or not base_url:
            continue
        try:
            result[(model_str, base_url)] = int(limit_str)
        except ValueError:
            continue
    return result


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class HermesAdapter(BaseAdapter):
    """Read-only provider adapter for a locally installed Hermes daemon.

    Suitable for test injection: pass ``hermes_home`` to redirect all paths
    and ``limit_registry`` to avoid global state pollution.
    """

    def __init__(
        self,
        hermes_home: Optional[Path] = None,
        limit_registry: Optional[ContextLimitRegistry] = None,
        socket_timeout: float = _SOCKET_TIMEOUT,
    ) -> None:
        self._home = hermes_home or (Path.home() / ".hermes")
        self._limit_registry = limit_registry if limit_registry is not None else ContextLimitRegistry()
        self._socket_timeout = socket_timeout

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return DISPLAY_NAME

    # ------------------------------------------------------------------
    # Internal: source reads
    # ------------------------------------------------------------------

    def _read_gateway(self) -> dict:
        """Try ``identify`` then ``status``; merge into one dict.

        Returns an empty dict if the socket is unreachable or either verb fails.
        Only the two read-only verbs are sent.
        """
        sock_path = str(self._home / "gateway.sock")
        merged: dict = {}
        for verb in ("identify", "status"):
            try:
                resp = _ask_gateway(sock_path, verb, self._socket_timeout)
                if isinstance(resp, dict):
                    merged.update(resp)
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        return merged

    def _load_limit_cache(self) -> None:
        """Parse context_length_cache.yaml and register observed limits.

        Silent no-op if the file is missing, unreadable, or unparseable.
        Entries with invalid limits are skipped.
        """
        cache_path = self._home / "context_length_cache.yaml"
        try:
            text = cache_path.read_text(encoding="utf-8")
        except (OSError, PermissionError):
            return
        try:
            entries = _parse_limit_cache(text)
        except Exception:  # pragma: no cover — parser should never raise
            return
        for (model_str, base_url), limit_val in entries.items():
            try:
                self._limit_registry.register_observed_limit(
                    PROVIDER_ID, model_str, base_url, limit_val
                )
            except (ValueError, TypeError):
                pass

    def _read_db(
        self,
    ) -> Tuple[List[dict], Dict[str, int], Optional[str]]:
        """Open state.db read-only and return (session_rows, compaction_map, error_or_None).

        Uses ``mode=ro`` URI — never ``immutable=1``.
        The compaction map is ``{session_id: count_of_compression_tasks}``.
        """
        db_path = self._home / "state.db"
        uri = f"file:{db_path}?mode=ro"
        try:
            con = sqlite3.connect(uri, uri=True, timeout=1.0)
        except sqlite3.OperationalError as exc:
            return [], {}, f"db_connect: {exc}"
        con.row_factory = sqlite3.Row
        try:
            sessions: List[dict] = [dict(row) for row in con.execute(_SESSION_SQL)]
        except sqlite3.DatabaseError as exc:
            con.close()
            return [], {}, f"db_query_sessions: {exc}"
        compaction: Dict[str, int] = {}
        try:
            for row in con.execute(_COMPACTION_SQL):
                compaction[row["session_id"]] = row["compaction_count"]
        except sqlite3.DatabaseError:
            pass  # table may not exist; not fatal
        con.close()
        return sessions, compaction, None

    # ------------------------------------------------------------------
    # Internal: mapping
    # ------------------------------------------------------------------

    def _make_context(
        self,
        model: Optional[str],
        route: Optional[str],
        event_time: Optional[float],
    ) -> ContextMeasurement:
        """Build an UNAVAILABLE context measurement.

        The limit is populated from the registry when known (informational;
        percent_used remains None because semantic == UNAVAILABLE).
        """
        limit_result = self._limit_registry.get(PROVIDER_ID, model, route)
        return ContextMeasurement(
            semantic=ContextSemantic.UNAVAILABLE,
            used=None,
            limit=limit_result.limit,
            model=model,
            route=route,
            event_time=event_time,
            unavailable_reason=_CONTEXT_UNAVAILABLE_REASON,
        )

    def _map_session(
        self,
        row: dict,
        compaction_count: Optional[int],
    ) -> SessionRecord:
        """Map one ``sessions`` row to a ``SessionRecord``.

        Activity rules:
        - ``ended_at IS NOT NULL`` → ENDED (certain).
        - ``ended_at IS NULL``     → UNKNOWN (cannot distinguish idle from busy
          without the tui_gateway context verb).

        The ``active_sessions.json`` file is intentionally not consulted: it
        reads as empty even while agents are running (verified in ACC-02).
        """
        raw_model = row.get("model")
        model: Optional[str] = raw_model if raw_model else None

        raw_url = row.get("billing_base_url")
        # Pass the raw URL to _make_context; ContextLimitRegistry.get() normalizes.
        route: Optional[str] = raw_url if raw_url else None

        ended_at = row.get("ended_at")
        if ended_at is not None:
            activity = ActivityStatus.ENDED
            activity_provenance = "hermes.state_db: ended_at IS NOT NULL"
        else:
            activity = ActivityStatus.UNKNOWN
            activity_provenance = (
                "hermes.state_db: ended_at IS NULL; "
                "live activity indeterminate read-only"
            )

        raw_started = row.get("started_at")
        started_at: Optional[float] = (
            float(raw_started) if isinstance(raw_started, (int, float)) else None
        )
        raw_event = row.get("last_activity_at")
        event_time: Optional[float] = (
            float(raw_event) if isinstance(raw_event, (int, float)) else None
        )

        raw_msgs = row.get("message_count")
        messages_in_window: Optional[int] = (
            int(raw_msgs) if isinstance(raw_msgs, int) else None
        )

        return SessionRecord(
            provider_id=PROVIDER_ID,
            session_id=row.get("id") or "",
            parent_session_id=row.get("parent_session_id") or None,
            model=model,
            source=row.get("source") or None,
            event_time=event_time,
            started_at=started_at,
            activity=activity,
            activity_provenance=activity_provenance,
            context=self._make_context(model, route, event_time),
            messages_in_window=messages_in_window,
            messages_compacted=None,   # no confirmed column; see docs/discovery/hermes.md
            compaction_count=compaction_count,
        )

    # ------------------------------------------------------------------
    # BaseAdapter.collect
    # ------------------------------------------------------------------

    def collect(self) -> ProviderSnapshot:
        """Return a fresh snapshot of Hermes sessions.

        Reads from gateway.sock (identify + status) and state.db (mode=ro).
        Populates the limit registry from context_length_cache.yaml.
        Never modifies Hermes state.
        """
        observation_time = time.time()

        # Populate limit registry from the observed cache file.
        self._load_limit_cache()

        # Source A: gateway socket (version, liveness).
        gateway = self._read_gateway()
        source_version: Optional[str] = gateway.get("code_version") or None

        # Source B: state.db (session records).
        session_rows, compaction, db_error = self._read_db()

        if db_error:
            return ProviderSnapshot(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                source_status="error",
                source_version=source_version,
                observation_time=observation_time,
                error_code="db_unavailable",
                error_reason=db_error,
                sessions=[],
            )

        # DB is readable; provider data is available even if daemon is stopped.
        sessions = [
            self._map_session(row, compaction.get(row.get("id") or ""))
            for row in session_rows
        ]

        return ProviderSnapshot(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY_NAME,
            source_status="ok",
            source_version=source_version,
            observation_time=observation_time,
            sessions=sessions,
        )


def create_adapter() -> HermesAdapter:
    """Factory required by ``ProviderRegistry.load_from_manifest``."""
    return HermesAdapter()
