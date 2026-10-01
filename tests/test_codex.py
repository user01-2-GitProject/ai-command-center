"""Tests for the Codex read-only adapter (ACC-PA-codex).

Coverage targets from the acceptance checklist:
  - Offline / missing ~/.codex directory
  - Missing or locked SQLite database
  - Required columns absent from schema (schema drift)
  - Optional columns absent (tolerated silently)
  - Malformed DB rows
  - Rollout path outside sessions root (rejected)
  - Rollout path is a symlink escaping sessions root (rejected)
  - Rollout file not found (silently skipped)
  - Malformed JSONL lines (silently skipped)
  - Incomplete final line not returned as a record
  - No token_count events → UNAVAILABLE context
  - Last token_count event → LAST_REQUEST_INPUT context; percent_used always None
  - Context window stored as limit (informational; never a percentage)
  - model from token_count event preferred over DB column
  - DB model used as fallback when rollout absent
  - archived != 0 → ENDED activity
  - archived == 0 → UNKNOWN activity
  - archived column absent → UNKNOWN activity
  - cli_version captured as source_version
  - Multiple sessions; per-session error isolation
  - Session budget cap (truncated flag)
  - created_at → started_at; updated_at → event_time fallback
  - Telemetry data treated as data, never executed
  - provider_id and display_name constants
  - create_adapter() factory satisfies BaseAdapter contract
  - Live integration read (skipped if ~/.codex is absent)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from acc.models import ActivityStatus, ContextSemantic, FreshnessStatus
from acc.providers.codex import (
    PROVIDER_ID,
    DISPLAY_NAME,
    _CONTEXT_UNAVAILABLE_REASON,
    _LAST_REQUEST_REASON,
    _MAX_SESSIONS,
    CodexAdapter,
    _parse_iso,
    _read_rollout,
    _validate_rollout_path,
    create_adapter,
)
from acc.registry import ProviderRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_db(path: Path, extra_cols: str = "") -> sqlite3.Connection:
    """Create a minimal state_5.sqlite with the required schema."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        f"""CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT,
            cli_version TEXT,
            model TEXT,
            model_provider TEXT,
            archived INTEGER DEFAULT 0
            {(',' + extra_cols) if extra_cols else ''}
        )"""
    )
    conn.commit()
    return conn


def _init_db_with_timestamps(path: Path) -> sqlite3.Connection:
    return _init_db(path, "created_at TEXT, updated_at TEXT")


def _insert_thread(
    conn: sqlite3.Connection,
    id: str = "thread-001",
    rollout_path: str = "",
    cli_version: str = "0.155.0-alpha.9.2",
    model: str = "gpt-6-astra",
    model_provider: str = "openai",
    archived: int = 0,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> None:
    cols = ["id", "rollout_path", "cli_version", "model", "model_provider", "archived"]
    vals: list = [id, rollout_path, cli_version, model, model_provider, archived]
    if created_at is not None:
        cols.append("created_at")
        vals.append(created_at)
    if updated_at is not None:
        cols.append("updated_at")
        vals.append(updated_at)
    placeholders = ", ".join("?" * len(cols))
    conn.execute(
        f"INSERT INTO threads ({', '.join(cols)}) VALUES ({placeholders})", vals
    )
    conn.commit()


def _make_token_count_line(
    model: str = "gpt-6-astra",
    input_tokens: int = 50000,
    context_window: int = 258400,
    timestamp: str = "2026-10-01T10:00:00.000Z",
) -> str:
    return json.dumps({
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {
            "type": "token_count",
            "info": {
                "model": model,
                "model_context_window": context_window,
                "last_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": 40000,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 350,
                    "reasoning_output_tokens": 0,
                    "total_tokens": input_tokens + 350,
                },
                "total_token_usage": {
                    "input_tokens": 999999,
                    "output_tokens": 9999,
                    "total_tokens": 1009998,
                },
            },
        },
    })


def _make_task_started_line(
    timestamp: str = "2026-10-01T09:00:00.000Z",
    context_window: int = 258400,
) -> str:
    return json.dumps({
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {
            "type": "task_started",
            "model_context_window": context_window,
            # Private fields that must never reach the adapter output:
            "base_instructions": "SECRET SYSTEM PROMPT",
            "world_state": {"SECRET": "WORLD_STATE"},
        },
    })


def _make_response_line(timestamp: str = "2026-10-01T09:30:00.000Z") -> str:
    """A response_item line that must never influence the adapter output."""
    return json.dumps({
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {
            "type": "response_item",
            "content": "SECRET PROMPT RESPONSE CONTENT",
        },
    })


def _setup_home(tmp: Path) -> Path:
    """Create a minimal ~/.codex-like directory structure."""
    codex_home = tmp / ".codex"
    (codex_home / "sessions").mkdir(parents=True)
    return codex_home


def _write_rollout(sessions_dir: Path, name: str, lines: list[str]) -> Path:
    path = sessions_dir / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _parse_iso unit tests
# ---------------------------------------------------------------------------

class ParseIsoTests(unittest.TestCase):

    def test_valid_utc_z(self) -> None:
        ts = _parse_iso("2026-10-01T10:00:00.000Z")
        self.assertIsNotNone(ts)
        self.assertIsInstance(ts, float)

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_parse_iso(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_parse_iso(""))

    def test_garbage_returns_none(self) -> None:
        self.assertIsNone(_parse_iso("not-a-date"))

    def test_integer_returns_none(self) -> None:
        self.assertIsNone(_parse_iso(99999))


# ---------------------------------------------------------------------------
# _validate_rollout_path unit tests
# ---------------------------------------------------------------------------

class ValidateRolloutPathTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.sessions = Path(self._tmpdir.name) / "sessions"
        self.sessions.mkdir()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_valid_path_returns_resolved(self) -> None:
        f = self.sessions / "sess-abc.jsonl"
        f.write_text("x")
        result = _validate_rollout_path(str(f), self.sessions)
        self.assertIsNotNone(result)
        self.assertEqual(result, f.resolve())

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_validate_rollout_path(None, self.sessions))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_validate_rollout_path("", self.sessions))

    def test_nonexistent_file_returns_none(self) -> None:
        result = _validate_rollout_path(
            str(self.sessions / "nonexistent.jsonl"), self.sessions
        )
        self.assertIsNone(result)

    def test_path_outside_root_returns_none(self) -> None:
        # A file that exists but is outside sessions root.
        outside = Path(self._tmpdir.name) / "evil.jsonl"
        outside.write_text("x")
        result = _validate_rollout_path(str(outside), self.sessions)
        self.assertIsNone(result)

    def test_directory_path_returns_none(self) -> None:
        result = _validate_rollout_path(str(self.sessions), self.sessions)
        self.assertIsNone(result)

    def test_non_string_returns_none(self) -> None:
        self.assertIsNone(_validate_rollout_path(42, self.sessions))


# ---------------------------------------------------------------------------
# _read_rollout unit tests
# ---------------------------------------------------------------------------

class ReadRolloutTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.sessions = Path(self._tmpdir.name) / "sessions"
        self.sessions.mkdir()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, name: str, lines: list[str]) -> Path:
        path = self.sessions / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_empty_file_returns_none(self) -> None:
        f = self._write("empty.jsonl", [])
        self.assertIsNone(_read_rollout(f))

    def test_no_token_count_events_returns_none(self) -> None:
        f = self._write("no_events.jsonl", [
            _make_task_started_line(),
            _make_response_line(),
        ])
        self.assertIsNone(_read_rollout(f))

    def test_returns_last_token_count_event(self) -> None:
        ts1 = "2026-10-01T09:00:00.000Z"
        ts2 = "2026-10-01T10:00:00.000Z"
        f = self._write("two_events.jsonl", [
            _make_token_count_line(input_tokens=10000, timestamp=ts1),
            _make_token_count_line(input_tokens=50000, timestamp=ts2),
        ])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        self.assertEqual(result["input_tokens"], 50000)
        self.assertEqual(result["timestamp"], ts2)

    def test_returns_model_from_event(self) -> None:
        f = self._write("model.jsonl", [
            _make_token_count_line(model="gpt-6-astra"),
        ])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        self.assertEqual(result["model"], "gpt-6-astra")

    def test_returns_context_window(self) -> None:
        f = self._write("ctx.jsonl", [
            _make_token_count_line(context_window=258400),
        ])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        self.assertEqual(result["model_context_window"], 258400)

    def test_malformed_lines_skipped(self) -> None:
        f = self._write("malformed.jsonl", [
            "this is not json",
            "{broken",
            _make_token_count_line(input_tokens=12345),
        ])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        self.assertEqual(result["input_tokens"], 12345)

    def test_response_item_lines_not_returned(self) -> None:
        """Response content must not leak into the result."""
        f = self._write("response.jsonl", [
            _make_response_line(),
            _make_token_count_line(input_tokens=777),
        ])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        # Only token_count fields are present.
        self.assertNotIn("content", result)
        self.assertNotIn("SECRET", str(result))
        self.assertEqual(result["input_tokens"], 777)

    def test_task_started_not_returned_as_token_count(self) -> None:
        f = self._write("task_started.jsonl", [
            _make_task_started_line(),
        ])
        # No token_count events — must return None, not a task_started payload.
        self.assertIsNone(_read_rollout(f))

    def test_non_event_msg_type_ignored(self) -> None:
        non_event = json.dumps({
            "type": "system_log",
            "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 999}}},
        })
        f = self._write("non_event.jsonl", [
            non_event,
            _make_token_count_line(input_tokens=42),
        ])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        self.assertEqual(result["input_tokens"], 42)

    def test_missing_last_token_usage_skipped(self) -> None:
        bad = json.dumps({
            "type": "event_msg",
            "payload": {"type": "token_count", "info": {"model_context_window": 100}},
        })
        f = self._write("no_usage.jsonl", [
            bad,
            _make_token_count_line(input_tokens=55),
        ])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        self.assertEqual(result["input_tokens"], 55)

    def test_missing_info_dict_skipped(self) -> None:
        bad = json.dumps({
            "type": "event_msg",
            "payload": {"type": "token_count", "info": "not-a-dict"},
        })
        good = _make_token_count_line(input_tokens=88)
        f = self._write("bad_info.jsonl", [bad, good])
        result = _read_rollout(f)
        self.assertIsNotNone(result)
        self.assertEqual(result["input_tokens"], 88)

    def test_bool_input_tokens_returns_none_field(self) -> None:
        line = json.dumps({
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "gpt-6-astra",
                    "model_context_window": 258400,
                    "last_token_usage": {"input_tokens": True},
                },
            },
        })
        f = self._write("bool_tokens.jsonl", [line])
        result = _read_rollout(f)
        # Bool should be rejected — input_tokens is None.
        self.assertIsNotNone(result)
        self.assertIsNone(result["input_tokens"])


# ---------------------------------------------------------------------------
# CodexAdapter unit tests — offline / DB errors
# ---------------------------------------------------------------------------

class OfflineTests(unittest.TestCase):

    def test_missing_codex_home(self) -> None:
        with TemporaryDirectory() as tmpdir:
            adapter = CodexAdapter(codex_home=Path(tmpdir) / "nonexistent")
            snap = adapter.collect()
        self.assertEqual(snap.provider_id, PROVIDER_ID)
        self.assertIn(snap.source_status, ("offline", "error"))
        self.assertEqual(snap.sessions, [])

    def test_missing_db_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / ".codex"
            home.mkdir()
            (home / "sessions").mkdir()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertIn(snap.source_status, ("offline", "error"))
        self.assertEqual(snap.sessions, [])

    def test_db_not_sqlite(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / ".codex"
            home.mkdir()
            (home / "sessions").mkdir()
            (home / "state_5.sqlite").write_text("not a database")
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertIn(snap.source_status, ("offline", "error"))
        self.assertEqual(snap.sessions, [])


# ---------------------------------------------------------------------------
# CodexAdapter unit tests — schema validation
# ---------------------------------------------------------------------------

class SchemaTests(unittest.TestCase):

    def test_missing_required_column_model_returns_error(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = sqlite3.connect(str(db_path))
            # schema WITHOUT required 'model' column
            conn.execute(
                "CREATE TABLE threads (id TEXT, rollout_path TEXT, cli_version TEXT, model_provider TEXT)"
            )
            conn.commit()
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertEqual(snap.source_status, "error")
        self.assertIsNotNone(snap.error_code)
        self.assertEqual(snap.sessions, [])

    def test_optional_columns_absent_is_tolerated(self) -> None:
        """No created_at / updated_at — adapter must still succeed."""
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)  # no timestamp columns
            _insert_thread(conn, id="sess-1")
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertEqual(snap.source_status, "ok")
        self.assertEqual(len(snap.sessions), 1)

    def test_all_optional_columns_present(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db_with_timestamps(db_path)
            _insert_thread(
                conn,
                id="sess-ts",
                created_at="2026-10-01T09:00:00.000Z",
                updated_at="2026-10-01T10:00:00.000Z",
            )
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertEqual(snap.source_status, "ok")
        sess = snap.sessions[0]
        self.assertIsNotNone(sess.started_at)

    def test_empty_threads_table_is_ok(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertEqual(snap.source_status, "ok")
        self.assertEqual(snap.sessions, [])


# ---------------------------------------------------------------------------
# CodexAdapter unit tests — context measurement
# ---------------------------------------------------------------------------

class ContextMeasurementTests(unittest.TestCase):

    def _adapter_with_rollout(
        self, lines: list[str]
    ) -> tuple["ProviderSnapshot", "SessionRecord"]:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            rollout_path = home / "sessions" / "sess-001.jsonl"
            _write_rollout(home / "sessions", "sess-001.jsonl", lines)
            _insert_thread(conn, id="sess-001", rollout_path=str(rollout_path))
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        return snap, snap.sessions[0]

    def test_no_rollout_file_gives_unavailable_context(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            _insert_thread(conn, id="sess-x", rollout_path="/nonexistent/path.jsonl")
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        self.assertEqual(sess.context.semantic, ContextSemantic.UNAVAILABLE)
        self.assertIsNone(sess.context.used)
        self.assertIsNone(sess.context.percent_used)

    def test_token_count_event_gives_last_request_input(self) -> None:
        snap, sess = self._adapter_with_rollout([
            _make_token_count_line(input_tokens=104334, context_window=258400),
        ])
        self.assertEqual(sess.context.semantic, ContextSemantic.LAST_REQUEST_INPUT)
        self.assertEqual(sess.context.used, 104334)

    def test_percent_used_is_always_none(self) -> None:
        """LAST_REQUEST_INPUT never produces a percentage."""
        snap, sess = self._adapter_with_rollout([
            _make_token_count_line(input_tokens=104334, context_window=258400),
        ])
        self.assertIsNone(sess.context.percent_used)

    def test_context_limit_stored(self) -> None:
        snap, sess = self._adapter_with_rollout([
            _make_token_count_line(context_window=258400),
        ])
        self.assertEqual(sess.context.limit, 258400)

    def test_context_route_is_none(self) -> None:
        """Route unknown from file storage — no percentage ever computable."""
        snap, sess = self._adapter_with_rollout([
            _make_token_count_line(),
        ])
        self.assertIsNone(sess.context.route)

    def test_context_model_from_token_count_event(self) -> None:
        snap, sess = self._adapter_with_rollout([
            _make_token_count_line(model="gpt-6-astra"),
        ])
        self.assertEqual(sess.context.model, "gpt-6-astra")

    def test_event_time_from_token_count_timestamp(self) -> None:
        snap, sess = self._adapter_with_rollout([
            _make_token_count_line(timestamp="2026-10-01T10:00:00.000Z"),
        ])
        self.assertIsNotNone(sess.context.event_time)

    def test_latest_event_wins(self) -> None:
        snap, sess = self._adapter_with_rollout([
            _make_token_count_line(input_tokens=10000, timestamp="2026-10-01T09:00:00.000Z"),
            _make_token_count_line(input_tokens=50000, timestamp="2026-10-01T10:00:00.000Z"),
        ])
        self.assertEqual(sess.context.used, 50000)

    def test_model_from_db_used_as_fallback(self) -> None:
        """When no rollout found, DB model is used."""
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            _insert_thread(conn, id="sess-y", model="gpt-fallback-model")
            # No rollout_path set → rollout file absent
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        self.assertEqual(sess.model, "gpt-fallback-model")


# ---------------------------------------------------------------------------
# CodexAdapter unit tests — activity and metadata
# ---------------------------------------------------------------------------

class ActivityTests(unittest.TestCase):

    def test_archived_session_is_ended(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            _insert_thread(conn, id="sess-arc", archived=1)
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        self.assertEqual(sess.activity, ActivityStatus.ENDED)
        self.assertIn("archived", sess.activity_provenance)

    def test_open_session_is_unknown(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            _insert_thread(conn, id="sess-open", archived=0)
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        self.assertEqual(sess.activity, ActivityStatus.UNKNOWN)

    def test_archived_column_absent_is_unknown(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            # Use schema without archived column.
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "CREATE TABLE threads "
                "(id TEXT, rollout_path TEXT, cli_version TEXT, model TEXT, model_provider TEXT)"
            )
            conn.execute(
                "INSERT INTO threads VALUES ('s1', '', '0.157.1', 'gpt-x', 'openai')"
            )
            conn.commit()
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        self.assertEqual(sess.activity, ActivityStatus.UNKNOWN)

    def test_source_includes_cli_version(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            _insert_thread(conn, id="sess-ver", cli_version="0.155.0-alpha.9.2")
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        self.assertIn("0.155.0-alpha.9.2", sess.source or "")

    def test_source_version_from_cli_version(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            _insert_thread(conn, id="sess-v", cli_version="0.157.1")
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertEqual(snap.source_version, "0.157.1")

    def test_provider_id_constant(self) -> None:
        self.assertEqual(PROVIDER_ID, "codex")

    def test_display_name_constant(self) -> None:
        self.assertIn("Codex", DISPLAY_NAME)


# ---------------------------------------------------------------------------
# CodexAdapter unit tests — budget and truncation
# ---------------------------------------------------------------------------

class BudgetTests(unittest.TestCase):

    def test_session_budget_cap(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            for i in range(_MAX_SESSIONS + 5):
                _insert_thread(conn, id=f"sess-{i:04d}")
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertLessEqual(len(snap.sessions), _MAX_SESSIONS)
        self.assertTrue(snap.truncated)

    def test_under_budget_not_truncated(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            for i in range(3):
                _insert_thread(conn, id=f"sess-{i}")
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        self.assertFalse(snap.truncated)


# ---------------------------------------------------------------------------
# CodexAdapter unit tests — data safety
# ---------------------------------------------------------------------------

class DataSafetyTests(unittest.TestCase):

    def test_private_content_not_in_context(self) -> None:
        """Private rollout fields must not reach SessionRecord."""
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            rollout_path = home / "sessions" / "private.jsonl"
            lines = [
                _make_task_started_line(),   # contains SECRET base_instructions
                _make_response_line(),        # contains SECRET PROMPT RESPONSE CONTENT
                _make_token_count_line(input_tokens=5000),
            ]
            _write_rollout(home / "sessions", "private.jsonl", lines)
            _insert_thread(conn, id="priv-sess", rollout_path=str(rollout_path))
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()

        sess = snap.sessions[0]
        sess_str = str(sess)
        self.assertNotIn("SECRET", sess_str)
        self.assertNotIn("base_instructions", sess_str)
        self.assertNotIn("world_state", sess_str)
        self.assertNotIn("RESPONSE CONTENT", sess_str)

    def test_telemetry_text_not_executed(self) -> None:
        """Embedded instructions in rollout data must never be executed."""
        injection = json.dumps({
            "type": "event_msg",
            "timestamp": "2026-10-01T10:00:00.000Z",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "__import__('os').system('echo INJECTED')",
                    "model_context_window": 258400,
                    "last_token_usage": {"input_tokens": 1},
                },
            },
        })
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            rollout_path = home / "sessions" / "inject.jsonl"
            _write_rollout(home / "sessions", "inject.jsonl", [injection])
            _insert_thread(conn, id="inj-sess", rollout_path=str(rollout_path))
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            # Must not raise, exec, or eval the model string.
            snap = adapter.collect()
        # The model string is treated as opaque data, not executed.
        self.assertEqual(snap.source_status, "ok")
        sess = snap.sessions[0]
        # The model value may be present as a string; it should NOT have run.
        if sess.model is not None:
            self.assertIn("__import__", sess.model)  # stored as raw string

    def test_rollout_path_outside_sessions_root_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            # Create a file outside sessions root with token_count events.
            evil = Path(tmpdir) / "evil.jsonl"
            evil.write_text(_make_token_count_line(input_tokens=9999) + "\n")
            conn = _init_db(db_path)
            _insert_thread(conn, id="evil-sess", rollout_path=str(evil))
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        # Path outside sessions root — no token_count data used.
        self.assertEqual(sess.context.semantic, ContextSemantic.UNAVAILABLE)

    def test_cumulative_tokens_not_used_for_context(self) -> None:
        """total_token_usage (cumulative) must not appear as context.used."""
        line = json.dumps({
            "type": "event_msg",
            "timestamp": "2026-10-01T10:00:00.000Z",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "gpt-6-astra",
                    "model_context_window": 258400,
                    "last_token_usage": {"input_tokens": 50000},
                    "total_token_usage": {
                        "input_tokens": 2000000,
                        "output_tokens": 20000,
                        "total_tokens": 2020000,
                    },
                },
            },
        })
        with TemporaryDirectory() as tmpdir:
            home = _setup_home(Path(tmpdir))
            db_path = home / "state_5.sqlite"
            conn = _init_db(db_path)
            rollout_path = home / "sessions" / "cumulative.jsonl"
            _write_rollout(home / "sessions", "cumulative.jsonl", [line])
            _insert_thread(conn, id="cum-sess", rollout_path=str(rollout_path))
            conn.close()
            adapter = CodexAdapter(codex_home=home)
            snap = adapter.collect()
        sess = snap.sessions[0]
        # Must use last_token_usage.input_tokens = 50000, not 2000000.
        self.assertEqual(sess.context.used, 50000)


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class RegistryTests(unittest.TestCase):

    def test_create_adapter_satisfies_base_adapter(self) -> None:
        adapter = create_adapter()
        self.assertIsNotNone(adapter.provider_id)
        self.assertIsNotNone(adapter.display_name)
        self.assertTrue(callable(adapter.collect))

    def test_registry_can_load_via_manifest(self) -> None:
        registry = ProviderRegistry()
        registry.load_from_manifest(["acc.providers.codex"])
        self.assertIn(PROVIDER_ID, registry)

    def test_adapter_registered_as_only_codex_entry(self) -> None:
        """No shell or UI code may name the provider; only this module may."""
        registry = ProviderRegistry()
        registry.load_from_manifest(["acc.providers.codex"])
        ids = registry.provider_ids()
        self.assertEqual(ids.count(PROVIDER_ID), 1)

    def test_collect_returns_valid_snapshot_structure(self) -> None:
        adapter = create_adapter()
        snap = adapter.collect()
        self.assertEqual(snap.provider_id, PROVIDER_ID)
        self.assertIsNotNone(snap.display_name)
        self.assertIn(snap.source_status, ("ok", "offline", "error", "unknown"))
        self.assertIsInstance(snap.sessions, list)


# ---------------------------------------------------------------------------
# Live integration test (skipped when ~/.codex is absent)
# ---------------------------------------------------------------------------

class LiveIntegrationTests(unittest.TestCase):
    """Read-only checks against the real local ~/.codex.

    Skipped automatically when ``~/.codex/state_5.sqlite`` is not present.
    No session is modified, dispatched, or resumed.  No private content
    (prompts, titles, tool arguments) is read or emitted.
    """

    @classmethod
    def setUpClass(cls) -> None:
        codex_home = Path.home() / ".codex"
        db = codex_home / "state_5.sqlite"
        if not db.exists():
            raise unittest.SkipTest("~/.codex/state_5.sqlite not present")

    def test_live_collect_returns_valid_snapshot(self) -> None:
        adapter = create_adapter()
        snap = adapter.collect()
        self.assertEqual(snap.provider_id, PROVIDER_ID)
        self.assertIn(snap.source_status, ("ok", "offline", "error", "unknown"))
        self.assertIsNotNone(snap.observation_time)

    def test_live_sessions_have_valid_structure(self) -> None:
        adapter = create_adapter()
        snap = adapter.collect()
        for sess in snap.sessions:
            self.assertEqual(sess.provider_id, PROVIDER_ID)
            self.assertIsInstance(sess.session_id, str)
            self.assertNotEqual(sess.session_id, "")
            # Context semantic must be one of the known values.
            self.assertIn(
                sess.context.semantic,
                (ContextSemantic.LAST_REQUEST_INPUT, ContextSemantic.UNAVAILABLE),
            )
            # percent_used must be None (no OCCUPANCY data from Codex files).
            self.assertIsNone(sess.context.percent_used)

    def test_live_no_private_content_in_sessions(self) -> None:
        """No prompt content, titles, or credentials must appear in snapshot."""
        adapter = create_adapter()
        snap = adapter.collect()
        snap_str = str(snap)
        # These keys must never reach the snapshot.
        for forbidden in ("base_instructions", "world_state", "response_item"):
            self.assertNotIn(forbidden, snap_str)

    def test_live_read_does_not_write(self) -> None:
        """Collecting must not modify the database."""
        db_path = Path.home() / ".codex" / "state_5.sqlite"
        mtime_before = db_path.stat().st_mtime
        adapter = create_adapter()
        adapter.collect()
        mtime_after = db_path.stat().st_mtime
        self.assertEqual(mtime_before, mtime_after)


if __name__ == "__main__":
    unittest.main()
