"""Bounded read-only consumer of the canonical ACC-08 metadata contract.

No prompt, title, filesystem locator or route is exported. Historical request
input never feeds occupancy. Worker threads are daemon readers (not provider
processes); a hung source gets at most one in-flight read until it returns.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import threading
import time
import weakref
from concurrent.futures import Future, wait
from dataclasses import replace

from acc.models import (ActivityStatus, ContextMeasurement, ContextSemantic,
                        ProviderSnapshot, SessionRecord, freshness_of)
from acc.registry import ProviderRegistry


def timestamp(value):
    # Compare before float conversion: arbitrarily large ints overflow isfinite.
    # These are the UTC datetime bounds; invalid telemetry remains unknown.
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not -62135596800 <= value < 253402300800):
        return None
    try:
        return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def age_class(value, now):
    return freshness_of(value if timestamp(value) else None, now).value


def text(value):
    return value[:256] if isinstance(value, str) else None


def token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**53 - 1 else None


def session_view(row, snapshot, now):
    context = row.context
    semantic = context.semantic.value
    event_freshness = age_class(row.event_time, now)
    context_freshness = age_class(context.event_time, now)
    source_freshness = age_class(snapshot.observation_time, now)
    source_ok = snapshot.source_status == 'ok' and source_freshness == 'fresh'
    stale = not source_ok or event_freshness != 'fresh'
    activity = row.activity.value
    if stale and activity != ActivityStatus.ENDED.value:
        activity = ActivityStatus.UNKNOWN.value
    identity_verified = bool(context.model and context.route) and context.model == row.model
    counts_valid = token_count(context.used) is not None and token_count(context.limit) is not None
    percent = None
    if (source_ok and identity_verified and counts_valid and context.limit > 0
            and semantic == 'occupancy' and context_freshness in ('fresh', 'stale')):
        # Use the validated timestamp and this payload's clock, not coercive
        # canonical property conversion or a second wall-clock observation.
        percent = context.used / context.limit * 100.0
    reason = 'Historical request input, not current context occupancy.' if semantic == 'last_request_input' else 'Verified occupancy is unavailable.'
    return {
        'provider': text(snapshot.display_name), 'provider_id': snapshot.provider_id,
        'session_id': row.session_id, 'parent_session_id': row.parent_session_id,
        'model': text(row.model), 'route_verified': bool(context.route),
        'source': text(row.source), 'source_version': text(snapshot.source_version),
        'source_status': snapshot.source_status,
        'activity': activity, 'activity_provenance': text(row.activity_provenance),
        'context_semantic': semantic, 'context_freshness': context_freshness,
        'session_freshness': event_freshness, 'source_freshness': source_freshness,
        'context_event_time': timestamp(context.event_time), 'context_reason': reason,
        'last_request_input': token_count(context.used) if semantic == 'last_request_input' else None,
        'context_used': token_count(context.used) if percent is not None else None,
        'context_limit': token_count(context.limit) if percent is not None else None,
        'reported_context_window': token_count(context.limit),
        'percent_used': percent, 'messages_in_window': token_count(row.messages_in_window),
        'messages_compacted': token_count(row.messages_compacted),
        'compaction_count': token_count(row.compaction_count),
        'session_age_sec': int(now - row.started_at) if timestamp(row.started_at) and row.started_at <= now else None,
        'last_update': timestamp(row.event_time), 'observed_at': timestamp(snapshot.observation_time),
        'stale': stale, 'freshness': 'stale' if not source_ok else event_freshness,
        'age_sec': int(now - row.event_time) if timestamp(row.event_time) and row.event_time <= now else None,
        'error': snapshot.error_code if snapshot.source_status != 'ok' else None,
        'unavailable_reason': reason if percent is None else None,
        'tools': [], 'tools_available': False,
        'sample': False, 'percentage_reason': None if percent is not None else 'unavailable',
    }


def checked_snapshot(snapshot, adapter):
    """Reject shape/identity drift and detach cached records from the adapter."""
    if not isinstance(snapshot, ProviderSnapshot) or snapshot.provider_id != adapter.provider_id:
        raise ValueError('invalid_snapshot')
    if snapshot.source_status not in ('ok', 'offline', 'error', 'unknown'):
        raise ValueError('invalid_snapshot')
    if not isinstance(snapshot.sessions, list) or len(snapshot.sessions) > 200:
        raise ValueError('invalid_snapshot')
    rows = []
    for row in snapshot.sessions:
        if (not isinstance(row, SessionRecord) or row.provider_id != adapter.provider_id
                or not isinstance(row.session_id, str) or not 0 < len(row.session_id) <= 128
                or (row.parent_session_id is not None and not isinstance(row.parent_session_id, str))
                or not isinstance(row.activity, ActivityStatus)
                or (row.model is not None and not isinstance(row.model, str))
                or not isinstance(row.context, ContextMeasurement)
                or not isinstance(row.context.semantic, ContextSemantic)
                or (row.context.model is not None and not isinstance(row.context.model, str))
                or (row.context.route is not None and not isinstance(row.context.route, str))):
            raise ValueError('invalid_snapshot')
        rows.append(replace(row, context=replace(row.context)))
    error_code = snapshot.error_code
    if not isinstance(error_code, str) or not re.fullmatch(r'[a-z0-9_]{1,64}', error_code):
        error_code = 'source_error' if snapshot.source_status == 'error' else None
    return replace(snapshot, display_name=adapter.display_name, sessions=rows,
                   error_code=error_code, error_reason=None)


class RegistryLabels:
    """Compatibility labels; plugin ownership stays in the canonical registry."""
    def __init__(self, canonical):
        self.canonical = canonical

    def names(self):
        return [adapter.display_name for adapter in self.canonical.adapters()]


class LivePoller:
    def __init__(self, registry: ProviderRegistry, *, interval_sec: float = 15,
                 timeout_sec: float = 10):
        for value in (interval_sec, timeout_sec):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError('poll interval and timeout must be positive finite numbers')
        self.canonical_registry = registry
        self.registry = RegistryLabels(registry)
        self.interval_sec = interval_sec
        self.timeout_sec = timeout_sec
        self._snapshots = {}
        self._last_success = {}
        self._inflight = {}
        # A retired ID blocks new reads until its old reader finishes. Keep
        # only the Future, not the adapter or any last-known session evidence.
        self._retired = {}
        self._reader_lock = threading.Lock()
        self._last_poll = None
        self._poll_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._closed = threading.Event()

    @staticmethod
    def _collect(adapter, future):
        try:
            future.set_result(adapter.collect())
        except Exception:
            # Do not transport exception strings, paths or tracebacks.
            future.set_exception(RuntimeError('adapter_exception'))

    def _failure(self, adapter, code):
        with self._cache_lock:
            previous = self._snapshots.get(adapter.provider_id)
            self._snapshots[adapter.provider_id] = ProviderSnapshot(
                provider_id=adapter.provider_id, display_name=adapter.display_name,
                source_status='error', source_version=previous.source_version if previous else None,
                observation_time=previous.observation_time if previous else None,
                error_code=code, sessions=previous.sessions if previous else [],
                truncated=previous.truncated if previous else False)

    def _retire_readers(self, active):
        callbacks = []
        removed = set()
        with self._reader_lock:
            for pid, (adapter, future) in list(self._inflight.items()):
                if active.get(pid) is adapter:
                    continue
                del self._inflight[pid]
                removed.add(pid)
                if not future.done():
                    self._retired[pid] = future
                    callbacks.append((pid, future))
        with self._cache_lock:
            removed.update(self._snapshots.keys() - active.keys())
            removed.update(self._last_success.keys() - active.keys())
            for pid in removed:
                self._snapshots.pop(pid, None)
                self._last_success.pop(pid, None)

        owner = weakref.ref(self)
        for pid, future in callbacks:
            def reap(done, pid=pid):
                poller = owner()
                if poller is not None:
                    with poller._reader_lock:
                        if poller._retired.get(pid) is done:
                            del poller._retired[pid]
            # Future invokes this synchronously if completion won the race.
            # Publish first, then attach with no reader/cache lock held; the
            # callback never takes _poll_lock (which this caller still owns).
            future.add_done_callback(reap)

    def poll_once(self):
        if self._closed.is_set() or not self._poll_lock.acquire(blocking=False):
            return False
        try:
            adapters = list(self.canonical_registry.adapters())
            self._retire_readers({adapter.provider_id: adapter for adapter in adapters})
            for adapter in adapters:
                pid = adapter.provider_id
                with self._reader_lock:
                    if pid in self._inflight or pid in self._retired:
                        continue
                    future = Future()
                    self._inflight[pid] = (adapter, future)
                threading.Thread(target=self._collect, args=(adapter, future),
                                 daemon=True, name='acc-metadata-reader').start()
            with self._reader_lock:
                pending = [future for _, future in self._inflight.values()]
            if pending:
                wait(pending, timeout=self.timeout_sec)
            for adapter in adapters:
                with self._reader_lock:
                    entry = self._inflight.get(adapter.provider_id)
                    if entry is None:
                        # This ID is still blocked by a retired reader. It
                        # neither spends the active timeout nor exports cache.
                        continue
                    original, future = entry
                    done = future.done()
                    if done:
                        del self._inflight[adapter.provider_id]
                if not done:
                    self._failure(adapter, 'timeout')
                    continue
                if original is not adapter:
                    self._failure(adapter, 'adapter_changed')
                    continue
                try:
                    snapshot = checked_snapshot(future.result(), adapter)
                except ValueError:
                    self._failure(adapter, 'invalid_snapshot')
                    continue
                except Exception:
                    self._failure(adapter, 'adapter_exception')
                    continue
                with self._cache_lock:
                    previous = self._snapshots.get(adapter.provider_id)
                    if snapshot.source_status == 'ok':
                        self._last_success[adapter.provider_id] = snapshot.observation_time
                    elif previous:
                        # Disconnected reads never erase or refresh last-known evidence.
                        snapshot = replace(snapshot, sessions=previous.sessions,
                                           source_version=previous.source_version,
                                           observation_time=previous.observation_time,
                                           truncated=previous.truncated)
                    self._snapshots[adapter.provider_id] = snapshot
            with self._cache_lock:
                self._last_poll = time.time()
            return True
        finally:
            self._poll_lock.release()

    def payload(self, mode='live'):
        now = time.time()
        with self._cache_lock:
            snapshots = dict(self._snapshots)
            last_success = dict(self._last_success)
            last_poll = self._last_poll
        providers, sessions = {}, []
        for adapter in self.canonical_registry.adapters():
            snapshot = snapshots.get(adapter.provider_id)
            source_age = age_class(snapshot.observation_time, now) if snapshot else 'unknown'
            status = {'ok': 'connected', 'offline': 'disconnected', 'error': 'error'}.get(snapshot.source_status, 'unknown') if snapshot else 'unknown'
            if status == 'connected' and source_age != 'fresh':
                status = 'stale'
            providers[adapter.provider_id] = {
                'status': status, 'display_name': text(adapter.display_name),
                'source_version': text(snapshot.source_version) if snapshot else None,
                'last_success': timestamp(last_success.get(adapter.provider_id)),
                'error_kind': snapshot.error_code if snapshot else None,
                'source_freshness': source_age,
                'truncated': bool(snapshot and snapshot.truncated),
            }
            try:
                # Do not partially extend the shared result if one row fails.
                rows = [session_view(row, snapshot, now) for row in snapshot.sessions] if snapshot else []
                json.dumps({'state': providers[adapter.provider_id], 'sessions': rows}, allow_nan=False)
            except Exception:
                providers[adapter.provider_id].update(status='error', error_kind='serialization_error',
                                                      source_freshness='unknown')
                rows = []
            sessions.extend(rows)
        provider_rows = []
        for adapter in self.canonical_registry.adapters():
            state = providers[adapter.provider_id]
            rows = [row for row in sessions if row['provider_id'] == adapter.provider_id]
            provider_rows.append({**state, 'provider': adapter.display_name,
                                  'provider_id': adapter.provider_id,
                                  'ok': state['status'] == 'connected',
                                  'error': state['error_kind'],
                                  'polled_at': timestamp(last_poll), 'sessions': rows})
        return {'mode': 'live', 'updated_at': timestamp(last_poll),
                'generated_at': timestamp(now), 'poll_interval_sec': self.interval_sec,
                'stale_after_sec': 30, 'providers': provider_rows,
                'provider_states': providers, 'sessions': sessions}

    def close(self):
        self._closed.set()
