"""Codex read-only adapter (ACC-PA-codex).

Read-only sources (per docs/discovery/codex.md):
  A. ~/.codex/state_5.sqlite       — session index (mode=ro, PRAGMA query_only=ON)
  B. ~/.codex/sessions/<rollout>   — JSONL event log; bounded tail read only

Context semantic is LAST_REQUEST_INPUT, derived from the most recent
``token_count`` event_msg in the rollout file.  This is a historical
per-response API-input value, not current context occupancy.
``percent_used`` is always None — never shown as a gauge.

The ``model_context_window`` from the same event is stored in ``context.limit``
for informational display only.  No percentage is computed because the provider
route is unknown from file storage alone (not read from credentials or config).

Explicitly excluded:
  - ~/.codex/log/, ~/.codex/auth*, ~/.codex/.env  — never opened.
  - DB columns: base_instructions, tokens_used, account fields, titles,
    preview, world_state, first_user_message — private content.
  - JSONL fields: response items, instructions, tool output, prompt text,
    titles, reasoning text — private content.
  - rollout_path is an internal locator; the resolved filesystem path never
    leaves the adapter.  Its value from the DB is used only to locate the file.
  - immutable=1 WAL mode — silently produces stale reads on live databases;
    never used.

Activity determination:
  - archived != 0 in the DB → ENDED.
  - Open sessions (archived == 0 or column absent) → UNKNOWN; cannot
    distinguish idle from busy by reading files alone.

Schema drift (per discovery doc):
  - Required columns {id, rollout_path, cli_version, model, model_provider}
    cause a source error if absent from the threads table.
  - Optional columns {archived, created_at, updated_at} are only selected
    when present; their absence is silently tolerated.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

from acc.models import (
    ActivityStatus,
    ContextMeasurement,
    ContextSemantic,
    ProviderSnapshot,
    SessionRecord,
)
from acc.registry import BaseAdapter

PROVIDER_ID = "codex"
DISPLAY_NAME = "Codex"

_DB_NAME = "state_5.sqlite"
_DB_CONNECT_TIMEOUT: float = 5.0     # seconds for sqlite3.connect
_DB_BUSY_TIMEOUT_MS: int = 3000      # PRAGMA busy_timeout

_MAX_TAIL_BYTES: int = 65_536         # 64 KiB per rollout file
_MAX_SESSIONS: int = 50               # session-budget cap

_CONTEXT_UNAVAILABLE_REASON: str = (
    "Codex last-response token_count event not found in rollout file. "
    "No context measurement available. See docs/discovery/codex.md."
)
_LAST_REQUEST_REASON: str = (
    "Codex last-request-input: input_tokens from the most recent token_count "
    "event in the rollout file. Not current context occupancy. "
    "Route is unknown from file storage; percent_used is always None."
)

# Required columns — source error if any is absent.
_DB_REQUIRED: FrozenSet[str] = frozenset({
    "id", "rollout_path", "cli_version", "model", "model_provider",
})
# Optional columns — selected only when present; absence is tolerated silently.
_DB_OPTIONAL: FrozenSet[str] = frozenset({"archived", "created_at", "updated_at"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso(value: object) -> Optional[float]:
    """Parse an ISO 8601 string to a Unix timestamp, or return None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None


def _validate_rollout_path(
    raw_path: object,
    sessions_root: Path,
) -> Optional[Path]:
    """Validate and return the rollout file path, or None.

    Rules:
    - raw_path must be a non-empty string.
    - The resolved path must be contained within sessions_root.
    - Symlinks that escape sessions_root are rejected.
    - Non-existent files return None silently (session may be archived/gone).
    """
    if not isinstance(raw_path, str) or not raw_path:
        return None
    try:
        candidate = Path(raw_path)
        # Resolve symlinks to detect escape attempts.
        resolved = candidate.resolve()
        sessions_resolved = sessions_root.resolve()
        if not str(resolved).startswith(str(sessions_resolved) + "/") and resolved != sessions_resolved:
            return None
        if not resolved.exists() or not resolved.is_file():
            return None
        return resolved
    except (OSError, ValueError):
        return None


def _read_rollout(path: Path) -> Optional[Dict]:
    """Read the last token_count event from a Codex rollout JSONL file.

    Returns a dict with keys:
        timestamp   (str | None)          — ISO 8601 event timestamp
        model       (str | None)          — model string from the event info
        input_tokens (int | None)         — last_token_usage.input_tokens
        model_context_window (int | None) — context window from the event

    Returns None if no qualifying event was found or on any IO error.

    Only event_msg records with payload.type == "token_count" are inspected.
    Explicitly excluded: response items, instructions, tool output, prompts,
    titles, reasoning text, and any other non-metric fields.

    Incomplete trailing lines (truncated mid-write) are silently skipped.
    Malformed complete lines are silently skipped without logging their content.
    """
    try:
        size = path.stat().st_size
        if size == 0:
            return None
        with path.open("rb") as fh:
            read_from = max(0, size - _MAX_TAIL_BYTES)
            fh.seek(read_from)
            chunk = fh.read(_MAX_TAIL_BYTES)
    except (OSError, PermissionError):
        return None

    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()

    # If we didn't start at byte 0, the first line may be cut mid-write.
    if read_from > 0 and len(lines) > 1:
        lines = lines[1:]

    last: Optional[Dict] = None

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Malformed complete line — skip without logging content.
            continue
        if not isinstance(record, dict):
            continue
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        usage = info.get("last_token_usage")
        if not isinstance(usage, dict):
            continue

        # Extract only the allowed numeric fields — never content or IDs.
        input_tokens = usage.get("input_tokens")
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool):
            input_tokens = None

        ctx_window = info.get("model_context_window")
        if not isinstance(ctx_window, int) or isinstance(ctx_window, bool):
            ctx_window = None

        model_str = info.get("model")
        if not isinstance(model_str, str) or not model_str:
            model_str = None

        last = {
            "timestamp": record.get("timestamp"),
            "model": model_str,
            "input_tokens": input_tokens,
            "model_context_window": ctx_window,
        }
        # Intentional: iterate all lines so `last` holds the latest event.

    return last


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class CodexAdapter(BaseAdapter):
    """Read-only provider adapter for a locally installed Codex desktop agent.

    Pass ``codex_home`` in tests to redirect all paths away from the real
    ``~/.codex`` directory.
    """

    def __init__(
        self,
        codex_home: Optional[Path] = None,
    ) -> None:
        self._home = codex_home or (Path.home() / ".codex")

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return DISPLAY_NAME

    # ------------------------------------------------------------------
    # Internal: schema introspection
    # ------------------------------------------------------------------

    @staticmethod
    def _introspect_columns(conn: sqlite3.Connection) -> FrozenSet[str]:
        """Return the set of column names in the threads table.

        Returns an empty frozenset on any error (no table, inaccessible, etc.).
        """
        try:
            rows = conn.execute("PRAGMA table_info(threads)").fetchall()
            return frozenset(row[1] for row in rows)
        except sqlite3.Error:
            return frozenset()

    # ------------------------------------------------------------------
    # Internal: database read
    # ------------------------------------------------------------------

    def _open_db(self) -> Tuple[Optional[sqlite3.Connection], Optional[str]]:
        """Open the Codex SQLite index in read-only mode.

        Returns (connection, None) on success, (None, error_reason) on failure.
        """
        db_path = self._home / _DB_NAME
        if not db_path.exists():
            return None, "db_not_found"
        uri = db_path.as_uri() + "?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=_DB_CONNECT_TIMEOUT)
            conn.execute("PRAGMA query_only=ON")
            conn.execute(f"PRAGMA busy_timeout={_DB_BUSY_TIMEOUT_MS}")
            conn.row_factory = sqlite3.Row
            return conn, None
        except sqlite3.OperationalError as exc:
            reason = str(exc)[:120]
            return None, f"db_open_error: {reason}"

    def _read_db_sessions(
        self, conn: sqlite3.Connection
    ) -> Tuple[List[Dict], Optional[str]]:
        """Read session rows from threads, respecting the column allowlist.

        Returns (rows_as_dicts, None) on success,
        ([], error_reason) if required columns are absent.
        Optional columns are only included when present in the schema.
        """
        available = self._introspect_columns(conn)
        if not available:
            return [], "schema_unreadable"

        missing_required = _DB_REQUIRED - available
        if missing_required:
            return [], f"missing_required_columns: {sorted(missing_required)}"

        optional_present = _DB_OPTIONAL & available
        all_cols = sorted(_DB_REQUIRED | optional_present)
        select_cols = ", ".join(all_cols)

        # Order by updated_at when available; fall back to id for stable ordering.
        order_col = "updated_at" if "updated_at" in available else "id"
        sql = (
            f"SELECT {select_cols} FROM threads "
            f"ORDER BY {order_col} DESC LIMIT {_MAX_SESSIONS}"
        )

        try:
            rows = conn.execute(sql).fetchall()
            return [dict(row) for row in rows], None
        except sqlite3.OperationalError as exc:
            reason = str(exc)[:120]
            return [], f"db_query_error: {reason}"

    # ------------------------------------------------------------------
    # Internal: mapping
    # ------------------------------------------------------------------

    def _make_context(
        self, token_info: Optional[Dict]
    ) -> ContextMeasurement:
        """Build a ContextMeasurement from rollout token_count data or UNAVAILABLE."""
        if not token_info:
            return ContextMeasurement(
                semantic=ContextSemantic.UNAVAILABLE,
                used=None,
                limit=None,
                unavailable_reason=_CONTEXT_UNAVAILABLE_REASON,
            )

        input_tokens = token_info.get("input_tokens")
        ctx_window = token_info.get("model_context_window")
        model_str = token_info.get("model") or None
        event_time = _parse_iso(token_info.get("timestamp"))

        # Validate numeric values — guard against truthy non-int (bool, float).
        used: Optional[int] = (
            input_tokens
            if isinstance(input_tokens, int) and not isinstance(input_tokens, bool)
            and input_tokens >= 0
            else None
        )
        limit: Optional[int] = (
            ctx_window
            if isinstance(ctx_window, int) and not isinstance(ctx_window, bool)
            and ctx_window > 0
            else None
        )

        return ContextMeasurement(
            semantic=ContextSemantic.LAST_REQUEST_INPUT,
            used=used,
            limit=limit,
            model=model_str,
            # Route unknown from file storage — no credentials/config read.
            route=None,
            event_time=event_time,
            unavailable_reason=None,
        )

    def _map_session(
        self,
        row: Dict,
        token_info: Optional[Dict],
    ) -> SessionRecord:
        """Map one DB row + optional rollout token info to a SessionRecord."""
        session_id: str = row.get("id") or ""
        db_model: Optional[str] = row.get("model") or None
        db_provider: Optional[str] = row.get("model_provider") or None
        cli_version: Optional[str] = row.get("cli_version") or None

        # Model: prefer the token_count event's model (bound to the measurement),
        # fall back to the DB model column.
        model: Optional[str] = (
            (token_info.get("model") if token_info else None) or db_model
        )

        # source: Codex-CLI (desktop runtime; no other source distinguishable
        # from file storage alone).
        source: Optional[str] = f"codex-cli/{cli_version}" if cli_version else "codex-cli"

        # Timestamps.
        started_at: Optional[float] = _parse_iso(row.get("created_at"))
        event_time: Optional[float]
        if token_info:
            event_time = _parse_iso(token_info.get("timestamp"))
        else:
            event_time = _parse_iso(row.get("updated_at"))

        # Activity from the archived column when present.
        archived = row.get("archived")
        if archived is not None and archived != 0:
            activity = ActivityStatus.ENDED
            activity_provenance = "codex.state_db: archived != 0"
        else:
            # Cannot distinguish idle from busy from file storage alone.
            activity = ActivityStatus.UNKNOWN
            activity_provenance = (
                "codex.state_db: archived == 0 (or column absent); "
                "live activity indeterminate read-only"
            )

        return SessionRecord(
            provider_id=PROVIDER_ID,
            session_id=session_id,
            parent_session_id=None,  # not verified from file storage
            model=model,
            source=source,
            event_time=event_time,
            started_at=started_at,
            activity=activity,
            activity_provenance=activity_provenance,
            context=self._make_context(token_info),
        )

    # ------------------------------------------------------------------
    # BaseAdapter.collect
    # ------------------------------------------------------------------

    def collect(self) -> ProviderSnapshot:
        """Return a fresh read-only snapshot of Codex sessions.

        Reads the SQLite index then the JSONL rollout tail for each session.
        Never modifies Codex state, opens credentials, or dispatches processes.
        """
        observation_time = time.time()
        sessions_root = self._home / "sessions"

        # Open the database.
        conn, db_error = self._open_db()
        if conn is None:
            return ProviderSnapshot(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                source_status="offline" if db_error == "db_not_found" else "error",
                source_version=None,
                observation_time=observation_time,
                error_code=db_error,
                error_reason=db_error,
                sessions=[],
            )

        try:
            db_rows, db_error = self._read_db_sessions(conn)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if db_error:
            return ProviderSnapshot(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                source_status="error",
                source_version=None,
                observation_time=observation_time,
                error_code=db_error,
                error_reason=db_error,
                sessions=[],
            )

        # Build session records.
        sessions: List[SessionRecord] = []
        source_version: Optional[str] = None

        for row in db_rows:
            # Locate the rollout file — internal use only; path never returned.
            rollout_path = _validate_rollout_path(
                row.get("rollout_path"), sessions_root
            )
            token_info = _read_rollout(rollout_path) if rollout_path else None

            sr = self._map_session(row, token_info)
            sessions.append(sr)

            # Track the most recent CLI version seen across sessions.
            ver = row.get("cli_version")
            if isinstance(ver, str) and ver:
                source_version = ver

        truncated = len(db_rows) == _MAX_SESSIONS

        return ProviderSnapshot(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY_NAME,
            source_status="ok",
            source_version=source_version,
            observation_time=observation_time,
            sessions=sessions,
            truncated=truncated,
        )


def create_adapter() -> CodexAdapter:
    """Factory required by ``ProviderRegistry.load_from_manifest``."""
    return CodexAdapter()
