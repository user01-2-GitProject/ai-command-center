'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { ageRow, agePayload, isBusy, isStale } = require('../ui/telemetry.js');
const now = Date.parse('2026-10-01T20:00:00Z');
const iso = (age) => new Date(now - age * 1000).toISOString();
const row = () => ({activity:'busy', context_semantic:'occupancy', freshness:'fresh',
  source_status:'ok', observed_at:iso(1), last_update:iso(2), context_event_time:iso(3),
  context_used:10, context_limit:100, percent_used:10});
test('fresh explicit busy is allowed; stale or unknown is not', () => {
  const current=ageRow(row(),now); assert.equal(isBusy(current),true);
  assert.equal(isBusy(ageRow({...row(),last_update:iso(45)},now)),false);
  assert.equal(isBusy(ageRow({...row(),activity:'unknown'},now)),false);
});
test('historical input never becomes occupancy', () => {
  const result=ageRow({...row(),context_semantic:'last_request_input'},now);
  assert.equal(result.percent_used,null); assert.equal(result.context_used,null);
});
test('expired context ages independently of session and source', () => {
  const result=ageRow({...row(),context_event_time:iso(301)},now);
  assert.equal(result.context_freshness,'expired'); assert.equal(result.percent_used,null);
  assert.equal(result.session_freshness,'fresh');
});
test('missing/nonparseable/future timestamps are unknown', () => {
  for (const last_update of [null,'nonsense',iso(-20)]) {
    const result=ageRow({...row(),last_update},now);
    assert.equal(result.session_freshness,'unknown'); assert.equal(isStale(result),true);
    assert.equal(isBusy(result),false);
  }
});
test('transport failure suppresses cached occupancy and activity without refreshing time', () => {
  const input={mode:'live',providers:[{provider:'Test',ok:true,status:'connected',last_success:iso(1),sessions:[row()]}]};
  const result=agePayload(input,now,true);
  const cached=result.providers[0].sessions[0];
  assert.equal(cached.percent_used,null); assert.equal(cached.activity,'unknown');
  assert.equal(cached.observed_at,input.providers[0].sessions[0].observed_at);
  assert.equal(result.providers[0].status,'unreachable');
  assert.equal(input.providers[0].sessions[0].percent_used,10);
});
test('a stale source cannot keep a busy robot or percentage alive', () => {
  const result=ageRow({...row(),observed_at:iso(35)},now);
  assert.equal(result.source_freshness,'stale'); assert.equal(result.percent_used,null);
  assert.equal(isBusy(result),false);
});
test('cached displayed event and session ages advance without cumulative drift', () => {
  const input={mode:'live',generated_at:new Date(now).toISOString(),providers:[{provider:'Synthetic fixture',sessions:[{...row(),age_sec:2,session_age_sec:100}]}]};
  let cached=agePayload(input,now,true);
  for(const ms of [500,1100,1500,2100,400000]) cached=agePayload(cached,now+ms,true);
  const current=cached.providers[0].sessions[0];
  assert.equal(current.age_sec,402);
  assert.equal(current.session_age_sec,500);
  assert.equal(current.session_freshness,'expired');
  assert.equal(input.providers[0].sessions[0].age_sec,2);
  assert.equal(agePayload(cached,now+400000,true).providers[0].sessions[0].session_age_sec,500);
});
test('missing/future event ages and unknown session ages remain unknown', () => {
  for(const last_update of [null,'nonsense',iso(-20)]) {
    const current=ageRow({...row(),last_update,age_sec:2,session_age_sec:null},now+10000,true);
    assert.equal(current.age_sec,null);
    assert.equal(current.session_age_sec,null);
  }
});
test('legacy working is permitted only for explicitly labeled demo', () => {
  assert.equal(isBusy({activity:'working',freshness:'fresh'},false),false);
  assert.equal(isBusy({activity:'working',freshness:'fresh'},true),true);
});
