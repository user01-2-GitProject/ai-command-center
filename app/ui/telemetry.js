/* Consumer-only aging policy; shared with dependency-free Node tests. */
(function (root, factory) {
  const policy = factory();
  if (typeof module === 'object' && module.exports) module.exports = policy;
  else root.ACC_TELEMETRY = policy;
})(globalThis, function () {
  'use strict';
  function freshness(iso, now) {
    const value = typeof iso === 'string' ? Date.parse(iso) : NaN;
    const age = (now - value) / 1000;
    return !Number.isFinite(age) || age < 0 ? 'unknown' : age <= 30 ? 'fresh' : age <= 300 ? 'stale' : 'expired';
  }
  function ageRow(row, now = Date.now(), disconnected = false, measuredAt = now) {
    const result = {...row};
    if (row.context_semantic === undefined) {
      if (disconnected) Object.assign(result, {freshness:'stale',activity:'unknown',percent_used:null,context_used:null,context_limit:null});
      return result; // Explicit legacy demo; never the live adapter path.
    }
    result.session_freshness = freshness(row.last_update,now);
    const updated = typeof row.last_update === 'string' ? Date.parse(row.last_update) : NaN;
    result.age_sec = Number.isFinite(updated) && updated <= now ? Math.floor((now-updated)/1000) : null;
    // Anchor the reported session age once, to server generation time. Keep
    // that anchor through repeated renders rather than adding rounded deltas.
    const start = Number.isFinite(row._session_age_origin_ms) ? row._session_age_origin_ms
      : Number.isSafeInteger(row.session_age_sec) && row.session_age_sec >= 0 && measuredAt <= now
        ? measuredAt - row.session_age_sec * 1000 : null;
    result._session_age_origin_ms = start;
    result.session_age_sec = Number.isFinite(start) && start <= now ? Math.floor((now-start)/1000) : null;
    result.context_freshness = freshness(row.context_event_time,now);
    result.source_freshness = freshness(row.observed_at,now);
    const sourceOK = !disconnected && row.source_status === 'ok' && result.source_freshness === 'fresh';
    result.stale = !sourceOK || result.session_freshness !== 'fresh';
    result.freshness = sourceOK ? result.session_freshness : 'stale';
    if (result.stale && result.activity !== 'ended') result.activity = 'unknown';
    if (!sourceOK || row.context_semantic !== 'occupancy' || !['fresh','stale'].includes(result.context_freshness)) {
      result.percent_used = null; result.context_used = null; result.context_limit = null;
    }
    if (disconnected) result.error = 'server_unreachable';
    return result;
  }
  function agePayload(payload, now = Date.now(), disconnected = false) {
    const generated = typeof payload.generated_at === 'string' ? Date.parse(payload.generated_at) : NaN;
    const measuredAt = Number.isFinite(generated) ? generated : now;
    return {...payload, providers: payload.providers.map(p => {
      const current = {...p, sessions:(p.sessions || []).map(s=>ageRow(s,now,disconnected,measuredAt))};
      if (disconnected) Object.assign(current,{ok:false,status:'unreachable',error:'server_unreachable'});
      else if (current.status === 'connected' && freshness(p.last_success,now) !== 'fresh') Object.assign(current,{ok:false,status:'stale'});
      return current;
    })};
  }
  function isStale(row) { return row.stale === true || row.freshness !== 'fresh'; }
  function isBusy(row, demo = false) {
    return !isStale(row) && (demo ? row.activity === 'working' : row.activity === 'busy' && row.source_status === 'ok' && row.source_freshness === 'fresh');
  }
  return Object.freeze({ageRow,agePayload,isBusy,isStale});
});
