'use strict';
/* Synthetic VM DOM and deterministic timers. No sources or browser profiles. */
const assert = require('node:assert/strict');
const {test} = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const telemetry = require('../ui/telemetry.js');

function harness(fetchImpl, Controller = AbortController) {
  class Element {
    constructor(tag = 'div') {
      this.tagName = tag; this.children = []; this.dataset = {}; this.style = {};
      this.hidden = true; this.attrs = {}; this.textContent = ''; this.listeners = {};
      this.classList = {toggle() {}};
    }
    appendChild(child) {
      if (child.parent) child.remove();
      this.children.push(child); child.parent = this; return child;
    }
    replaceChildren() { this.children.forEach(c => c.parent = null); this.children = []; }
    remove() { if(this.parent) this.parent.children = this.parent.children.filter(c => c !== this); this.parent = null; }
    setAttribute(key, value) { this.attrs[key] = value; }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    getBoundingClientRect() { return {width:390,height:80,left:0,top:0}; }
    getContext() { return new Proxy({}, {get:(_,key) => key === 'createRadialGradient' ? () => ({addColorStop(){}}) : () => {}}); }
    scrollIntoView() {}
    get offsetParent() { return null; }
    click() { this.listeners.click?.(); }
  }
  const nodes = new Map();
  const get = key => { if(!nodes.has(key)) nodes.set(key,new Element()); return nodes.get(key); };
  const root = get('root'); root.dataset.view = 'sector';
  const document = {documentElement:root, hidden:false, querySelector:get,
    querySelectorAll:() => get('#listBody').children,
    createElement:tag => new Element(tag), createTextNode:text => Object.assign(new Element('text'), {textContent:text}),
    addEventListener(){}};
  let seq = 0;
  const timeouts = new Map(), intervals = new Map();
  const context = vm.createContext({document, console, fetch:fetchImpl, AbortController:Controller,
    window:{ACC_TELEMETRY:telemetry, devicePixelRatio:1, matchMedia:() => ({matches:true,addEventListener(){}})},
    Image:class {}, ResizeObserver:class {observe() {}}, performance:{now:() => 0},
    setTimeout:(fn,ms) => { const id=++seq; timeouts.set(id,{fn,ms}); return id; },
    clearTimeout:id => timeouts.delete(id),
    setInterval:(fn,ms) => { const id=++seq; intervals.set(id,{fn,ms}); return id; },
    clearInterval:id => intervals.delete(id), requestAnimationFrame:() => ++seq, cancelAnimationFrame(){}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8'), context);
  return {context,nodes,timeouts,intervals, run:code => vm.runInContext(code,context),
    expire:() => { for(const [id,t] of [...timeouts]) { timeouts.delete(id); t.fn(); } }};
}
const flush = async () => { for(let n=0;n<20;n++) await Promise.resolve(); };
function metadata() {
  const now = new Date().toISOString();
  return {mode:'live',stale_after_sec:30,poll_interval_sec:15,providers:[{provider:'Synthetic fixture',provider_id:'fixture',
    ok:true,status:'connected',last_success:now,sessions:Array.from({length:8},(_,i) => ({provider:'Synthetic fixture',provider_id:'fixture',
      session_id:'fixture-'+i,source_status:'ok',activity:'busy',context_semantic:'occupancy',context_event_time:now,
      observed_at:now,last_update:now,percent_used:10,context_used:10,context_limit:100,source_freshness:'fresh'}))}]};
}

for (const phase of ['fetch','body','abort throws']) {
  test(`refresh bounds never-settling ${phase}, releases guard and reconnects`, async () => {
    let calls=0, signal;
    const Controller = phase === 'abort throws' ? class extends AbortController {abort(){super.abort();throw new Error('PRIVATE ABORT');}} : AbortController;
    const h = harness((_url, options) => {
      calls++; signal=options.signal;
      if(calls>1) return Promise.resolve({ok:true,json:async () => metadata()});
      return phase === 'body' ? Promise.resolve({ok:true,json:() => new Promise(()=>{})}) : new Promise(()=>{});
    }, Controller);
    await flush();
    assert.equal(h.run('refreshInFlight'),true);
    h.run('refresh()'); assert.equal(calls,1,'one bounded in-flight request');
    assert.ok(h.timeouts.size>0,'request/body deadline must be installed');
    assert.ok([...h.timeouts.values()].every(t => t.ms>0 && t.ms<=15000));
    h.expire(); await flush();
    assert.equal(signal.aborted,true);
    assert.equal(h.run('refreshInFlight'),false);
    assert.equal(h.nodes.get('#connError').hidden,false,'initial failure is visible');
    assert.equal(h.run('transportLost'),true);
    assert.ok(h.run('pollTimer') !== null,'reconnect timer installed');
    h.run('refresh()'); await flush();
    assert.equal(calls,2); assert.equal(h.run('refreshInFlight'),false);
    assert.equal(h.nodes.get('#connError').hidden,true);
    assert.equal(h.timeouts.size,0,'successful request clears deadline');
  });
}

for (const [view,motion] of [['sector',false],['sector',true],['list',false],['list',true]]) {
  test(`selecting beyond first six synchronizes tiles immediately in ${view}, motion ${motion}`, async () => {
    const h=harness(() => Promise.resolve({ok:true,json:async () => metadata()}));
    await flush();
    h.run(`setMotion(${motion});setView('${view}');select(sessionKey(allSessions()[7]),{scroll:false})`);
    assert.equal(h.run('tiles.some(t=>t.s?.session_id==="fixture-7")'),true);
    assert.equal(h.run('tiles.some(t=>t.s?.session_id==="fixture-5")'),false);
    assert.equal(h.run('tiles.length'),6);
    assert.equal(h.run('tiles.find(t=>t.s?.session_id==="fixture-7").el.attrs["aria-selected"]'),'true');
    h.run('setView("sector")');
    assert.equal(h.run('tiles.some(t=>t.s?.session_id==="fixture-7")'),true);
    h.run('document.querySelector("#detailX").click()');
    assert.equal(h.run('tiles.some(t=>t.s?.session_id==="fixture-5")'),true);
    assert.equal(h.run('tiles.some(t=>t.s?.session_id==="fixture-7")'),false);
  });
}

test('timed-out body downgrades cached metadata and cannot overwrite reconnect', async () => {
  let calls=0, late;
  const h=harness(() => {
    calls++;
    return Promise.resolve({ok:true,json:() => calls===2 ? new Promise(resolve => {late=resolve;}) : Promise.resolve(metadata())});
  });
  await flush();
  h.run('refresh()'); await flush(); h.expire(); await flush();
  assert.equal(h.run('transportLost'),true);
  assert.equal(h.run('allSessions().every(s => s.percent_used===null && s.activity==="unknown")'),true);
  assert.equal(h.run('payload.providers[0].status'),'unreachable');
  h.run('refresh()'); await flush();
  late({...metadata(),mode:'demo'}); await flush();
  assert.equal(h.run('payload.mode'),'live','late response is ignored');
  assert.equal(h.run('transportLost'),false);
});
