"""Claude Code read-only adapter (ACC-10).

Read-only sources (per docs/discovery/claude-code.md):
  A. ~/.claude/sessions/*.json     — process registrations (never .key files)
  B. ~/.claude/projects/*/<id>.jsonl — transcript tail for model and last-request usage

Context occupancy is UNAVAILABLE: no compatible denominator was found in sampled
registration or transcript data; the status-line hook that exposes per-session
occupancy was not installed (read-only task boundary).

The last assistant record's API-input token count uses ContextSemantic.LAST_REQUEST_INPUT.
This is a historical API-input value, not current context occupancy.  percent_used
is always None for LAST_REQUEST_INPUT — it must never be shown as a gauge.

Transcript content (prompts, tool inputs, tool arguments, titles, paths, account
fields, bridge identities, adjacent .key files) is NEVER extracted or returned.
Only record type, message.model, message.usage token counts, and timestamp are read.

Additional safety measures:
  - .key files adjacent to registration JSON are never opened.
  - Symlinks that resolve outside the configured source root are rejected.
  - Transcript reads are bounded to _MAX_TAIL_BYTES from the end of file.
  - Per-file errors are isolated; one bad file does not abort the collect.
  - /proc/<pid>/stat corroborates process presence but is not the primary signal;
    failure or absence in the check namespace renders liveness unknown, not offline.
"""

from __future__ import annotations

import datetime
import json
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

PROVIDER_ID = "claude_code"
DISPLAY_NAME = "Claude Code"

_MAX_TAIL_BYTES: int = 65_536   # 64 KiB read from transcript tail
_MAX_SESSIONS: int = 200        # cap on sessions returned

_CONTEXT_UNAVAILABLE_REASON: str = (
    "Claude Code context occupancy is not reachable read-only: "
    "no compatible denominator in sampled registration or transcript data; "
    "the status-line hook providing occupancy was not installed. "
    "See docs/discovery/claude-code.md."
)

_LAST_REQUEST_REASON: str = (
    "Claude Code last-request-input: historical API input from the final "
    "transcript assistant record. Not current context occupancy."
)

# Keys we actually extract from registration JSON.
# Anything not in this set is dropped — never name, cwd, project, socketPath,
# bridgeId, or any other path/identity field.
_REG_SAFE: frozenset = frozenset({
    "sessionId", "status", "version", "pid", "procStart",
    "updatedAt", "statusUpdatedAt",
})


# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------

def _parse_iso(value: object) -> Optional[float]:
    """Parse an ISO 8601 string to a Unix timestamp float, or return None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Process corroboration
# ---------------------------------------------------------------------------

def _process_corroborate(pid: object, proc_start: object) -> str:
    """Check /proc/<pid>/stat for process presence and start-tick match.

    Returns a short provenance string; never raises.
    The result is additional evidence, not the primary activity signal.
    """
    if not isinstance(pid, int) or pid <= 0:
        return "pid_invalid"
    proc_dir = Path("/proc") / str(pid)
    try:
        if not proc_dir.exists():
            return "pid_absent"
        stat_fields = (proc_dir / "stat").read_text().rsplit(")", 1)[1].split()
        if len(stat_fields) < 20:
            return "stat_parse_error"
        start_tick = stat_fields[19]
        if str(proc_start) == start_tick:
            return "pid_alive_start_match"
        return "pid_present_start_mismatch"
    except (OSError, IndexError, ValueError):
        return "proc_check_failed"


# ---------------------------------------------------------------------------
# Transcript tail reader
# ---------------------------------------------------------------------------

def _last_usage_record(path: Path) -> Optional[Dict]:
    """Return a safe dict from the last assistant record with usage in a transcript.

    Reads at most _MAX_TAIL_BYTES from the end of the file.  Only extracts
    model, usage token counts, and timestamp — never content or identifiers.

    Returns None if no qualifying record is found or on any IO error.
    """
    try:
        size = path.stat().st_size
        if size == 0:
            return None
        with path.open("rb") as f:
            read_from = max(0, size - _MAX_TAIL_BYTES)
            f.seek(read_from)
            chunk = f.read(_MAX_TAIL_BYTES)
    except (OSError, PermissionError):
        return None

    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    # If we didn't start from the beginning, the first line may be incomplete.
    if read_from > 0 and len(lines) > 1:
        lines = lines[1:]

    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue

        # Extract only safe, non-content token fields.
        safe: Dict = {}
        for key in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        ):
            val = usage.get(key)
            if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                safe[key] = val
        if not safe:
            continue

        # Model is a safe metadata string.
        model_val = message.get("model")
        if isinstance(model_val, str) and model_val:
            safe["model"] = model_val

        # Timestamp from the record (not the message content).
        ts_val = record.get("timestamp")
        if isinstance(ts_val, str) and ts_val:
            safe["timestamp"] = ts_val

        return safe

    return None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class ClaudeCodeAdapter(BaseAdapter):
    """Read-only adapter for locally running Claude Code sessions.

    Accepts *claude_home* for test injection (default: ``~/.claude``).
    """

    def __init__(
        self,
        claude_home: Optional[Path] = None,
        limit_registry: Optional[ContextLimitRegistry] = None,
    ) -> None:
        self._home = claude_home or (Path.home() / ".claude")
        self._limit_registry = (
            limit_registry if limit_registry is not None else ContextLimitRegistry()
        )

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return DISPLAY_NAME

    # ------------------------------------------------------------------
    # Internal: registrations
    # ------------------------------------------------------------------

    def _read_registrations(self) -> List[Dict]:
        """Read all *.json registration files from ~/.claude/sessions/.

        Skips:
          - Files ending in .key (adjacent credential files).
          - Symlinks resolving outside self._home.
          - Files that fail to parse as dicts.
        """
        sessions_dir = self._home / "sessions"
        if not sessions_dir.is_dir():
            return []
        result: List[Dict] = []
        for path in sessions_dir.glob("*.json"):
            if path.name.endswith(".key"):
                continue
            if path.is_symlink():
                try:
                    resolved = str(path.resolve())
                except OSError:
                    continue
                if not resolved.startswith(str(self._home)):
                    continue
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError, PermissionError, ValueError):
                continue
            if isinstance(data, dict):
                result.append(data)
            if len(result) >= _MAX_SESSIONS:
                break
        return result

    # ------------------------------------------------------------------
    # Internal: transcript lookup
    # ------------------------------------------------------------------

    def _find_transcript(self, session_id: str) -> Optional[Path]:
        """Find a parent session transcript at projects/*/<session_id>.jsonl.

        Returns None if not found or if the path is a symlink outside self._home.
        """
        if not session_id:
            return None
        projects_dir = self._home / "projects"
        if not projects_dir.is_dir():
            return None
        for candidate in projects_dir.glob(f"*/{session_id}.jsonl"):
            if candidate.is_symlink():
                try:
                    resolved = str(candidate.resolve())
                except OSError:
                    continue
                if not resolved.startswith(str(self._home)):
                    continue
            return candidate
        return None

    # ------------------------------------------------------------------
    # Internal: mapping
    # ------------------------------------------------------------------

    def _make_context(self, usage: Optional[Dict]) -> ContextMeasurement:
        """Build a ContextMeasurement from transcript usage or UNAVAILABLE."""
        if not usage:
            return ContextMeasurement(
                semantic=ContextSemantic.UNAVAILABLE,
                used=None,
                limit=None,
                unavailable_reason=_CONTEXT_UNAVAILABLE_REASON,
            )

        # Sum all input-side token counts for LAST_REQUEST_INPUT.
        total_input = sum(
            usage.get(k, 0)
            for k in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            )
        )
        model = usage.get("model") or None
        event_time = _parse_iso(usage.get("timestamp"))

        # No denominator in sampled data — limit stays None.
        return ContextMeasurement(
            semantic=ContextSemantic.LAST_REQUEST_INPUT,
            used=total_input if total_input >= 0 else None,
            limit=None,
            model=model,
            route=None,
            event_time=event_time,
            unavailable_reason=None,
        )

    def _map_registration(
        self,
        reg: Dict,
        usage: Optional[Dict],
    ) -> SessionRecord:
        """Map one registration dict + optional last usage to a SessionRecord."""
        session_id: str = reg.get("sessionId") or ""
        status_str: str = reg.get("status") or ""
        pid = reg.get("pid")
        proc_start = reg.get("procStart")
        version: Optional[str] = reg.get("version") or None

        # Activity from registration status.
        if status_str == "idle":
            activity = ActivityStatus.IDLE
        elif status_str == "busy":
            activity = ActivityStatus.BUSY
        else:
            activity = ActivityStatus.UNKNOWN

        # Optional process corroboration.
        proc_note = _process_corroborate(pid, proc_start)
        activity_provenance = (
            f"claude_code.registration: status={status_str!r}; proc={proc_note}"
        )

        # event_time from statusUpdatedAt (when status last changed) or updatedAt.
        event_time = _parse_iso(reg.get("statusUpdatedAt")) or _parse_iso(
            reg.get("updatedAt")
        )

        # Model from the transcript usage record (safer than registration).
        model: Optional[str] = (usage.get("model") if usage else None) or None

        return SessionRecord(
            provider_id=PROVIDER_ID,
            session_id=session_id,
            parent_session_id=None,   # parent/child link not in registration files
            model=model,
            source=None,              # source field not in registration; see transcript
            event_time=event_time,
            started_at=None,          # createdAt not confirmed in registration schema
            activity=activity,
            activity_provenance=activity_provenance,
            context=self._make_context(usage),
        )

    # ------------------------------------------------------------------
    # BaseAdapter.collect
    # ------------------------------------------------------------------

    def collect(self) -> ProviderSnapshot:
        """Return a fresh snapshot of Claude Code sessions.

        Reads registrations then optionally reads the last transcript record
        for each session.  Never modifies any file.
        """
        observation_time = time.time()

        registrations = self._read_registrations()
        if not registrations:
            # No sessions directory or no registration files is a valid state.
            return ProviderSnapshot(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                source_status="ok",
                source_version=None,
                observation_time=observation_time,
                sessions=[],
            )

        sessions: List[SessionRecord] = []
        source_version: Optional[str] = None

        for reg in registrations:
            session_id = reg.get("sessionId") or ""
            transcript = self._find_transcript(session_id)
            usage = _last_usage_record(transcript) if transcript else None

            sr = self._map_registration(reg, usage)
            sessions.append(sr)

            # Use the most recent CLI version seen across registrations.
            ver = reg.get("version")
            if isinstance(ver, str) and ver:
                source_version = ver

        return ProviderSnapshot(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY_NAME,
            source_status="ok",
            source_version=source_version,
            observation_time=observation_time,
            sessions=sessions,
        )


def create_adapter() -> ClaudeCodeAdapter:
    """Factory required by ``ProviderRegistry.load_from_manifest``."""
    return ClaudeCodeAdapter()
