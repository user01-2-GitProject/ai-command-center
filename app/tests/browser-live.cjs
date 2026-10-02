'use strict';
/* Real live-server QA. Own Chromium profile; no personal browser/cookies. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const base = process.env.ACC_QA_URL || 'http://127.0.0.1:8773';
const fixture = process.env.ACC_QA_FIXTURE === '1';
assert.equal(new URL(base).hostname, '127.0.0.1');
const out = path.resolve(process.env.ACC_QA_OUT || 'docs/verification/live-session-bridge');
fs.mkdirSync(out, {recursive:true});
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'acc19-chromium-'));
let chrome, socket, launchError;
const checks = [], errors = [], requests = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function ok(name) { checks.push(name); }
async function main() {
  chrome = spawn(process.env.ACC_CHROMIUM || '/usr/bin/chromium', ['--headless','--no-sandbox','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank'],{stdio:'ignore'});
  chrome.on('error',error => {launchError=error;});
  const active=path.join(profile,'DevToolsActivePort');
  for (let n=0;!fs.existsSync(active);n++) {
    if (launchError) throw new Error('Chromium executable unavailable');
    if (n>100 || chrome.exitCode !== null) throw new Error('Chromium startup failed');
    await sleep(100);
  }
  const port=fs.readFileSync(active,'utf8').split('\n')[0];
  const target=(await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let sequence=0;
  const pending=new Map();
  socket.onmessage=event=>{
    const message=JSON.parse(event.data);
    if (message.id) {
      const request=pending.get(message.id);
      if(request){pending.delete(message.id);message.error?request.reject(new Error(message.error.message)):request.resolve(message.result);}
    } else if (message.method==='Runtime.exceptionThrown') errors.push('runtime exception');
    else if(message.method==='Log.entryAdded' && message.params.entry.level==='error') errors.push(message.params.entry.text);
    else if(message.method==='Network.requestWillBeSent') requests.push(message.params.request.url);
  };
  async function call(method,params={}) {
    const id=++sequence;
    return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  }
  async function evaluate(expression) {
    const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails) throw new Error('Browser evaluation failed');
    return result.result.value;
  }
  async function until(expression) {
    for(let n=0;n<100;n++){if(await evaluate(expression))return;await sleep(100);}
    throw new Error('Browser condition did not become true');
  }
  async function screenshot(name) {
    const image=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    fs.writeFileSync(path.join(out,name),Buffer.from(image.data,'base64'));
  }
  async function visibleDetails() {
    return evaluate(`(() => {
      const panel=document.querySelector('#detailWin'), dl=document.querySelector('#detailDl');
      const visible=node => {
        for(let p=node;p;p=p.parentElement) {
          const css=getComputedStyle(p);
          if(p.hidden || css.display==='none' || css.visibility==='hidden' || css.opacity==='0') return false;
        }
        const r=node.getBoundingClientRect();
        return r.width>0 && r.height>0 && r.bottom>0 && r.top<innerHeight && r.right>0 && r.left<innerWidth;
      };
      return visible(panel) && visible(dl);
    })()`);
  }
  await call('Page.enable');await call('Runtime.enable');await call('Log.enable');await call('Network.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:base});
  await until('typeof payload !== "undefined" && payload && allSessions().length > 0 && !connError.hidden === false');
  assert.equal(await evaluate('payload.mode'), 'live');
  assert.equal(await evaluate('demoBanner.hidden'),true);
  const count=await evaluate('allSessions().length');
  assert.ok(count>0);
  if(fixture) assert.equal(await evaluate('allSessions().every(s=>s.provider_id==="fixture")'),true);
  else assert.equal(await evaluate('allSessions().every(s=>s.provider_id!=="fixture")'),true);
  ok(fixture ? 'Synthetic canonical-contract fixtures, NOT actual sources' : 'Real live sessions, not fixtures');
  assert.equal(await evaluate('allSessions().every(s=>s.percent_used===null)'),true);ok('Codex historical input is not occupancy');
  assert.equal(await evaluate('allSessions().every(s=>s.activity!=="working" && s.activity!=="busy")'),true);
  assert.equal(await evaluate('JSON.stringify(layout(0).map(e=>[e.x,e.y])) === JSON.stringify(layout(10).map(e=>[e.x,e.y]))'),true);ok('Unknown/stale agent positions remain stationary');
  assert.ok(await evaluate('sceneSessions().length <= 6 && tiles.length <= 6'));ok('Canvas work bounded, full list retained');
  await until('iggyIso.complete && iggyIso.naturalWidth > 0');ok('Original Iggy sprite decoded');
  await screenshot('desktop-live.png');
  await evaluate('setView("list")');
  assert.equal(await evaluate('document.querySelectorAll("#listBody tr").length'),count);ok('Every returned session appears in plain list');
  await evaluate('select(sessionKey(allSessions().find(s=>s.last_request_input!==null)))');
  assert.equal(await visibleDetails(),true,'List selection must visibly present details with nonzero viewport geometry');
  assert.equal(await evaluate('document.querySelector("#detailDl").textContent.includes("historical, not occupancy")'),true);
  assert.equal(await evaluate('document.querySelector("#detailDl").textContent.includes("Source version")'),true);ok('Details explain historical input, provenance and missing route');
  await screenshot('list-details-live.png');
  await evaluate('window.actualFetch=window.fetch;window.fetch=()=>Promise.reject(new Error("injected QA transport failure"));refresh()');
  assert.equal(await evaluate('connError.hidden'),false);
  assert.equal(await evaluate('allSessions().every(s=>s.percent_used===null && (s.activity==="unknown" || s.activity==="ended"))'),true);
  assert.equal(await evaluate('document.querySelector("#detailDl").textContent.includes("server_unreachable")'),true);ok('Transport failure updates cached rows and selected details');
  assert.equal(await visibleDetails(),true,'Downgraded detail metadata remains visibly presented');
  await evaluate('window.fetch=window.actualFetch;refresh()');
  assert.equal(await evaluate('connError.hidden'),true);ok('Reconnect restores actual metadata');
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await sleep(50);assert.equal(await evaluate('motionOn'),false);ok('Dynamic reduced motion stops decoration');
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate('setView("sector");document.querySelector("#detailX").click()');
  await sleep(150);
  if(fixture) assert.ok(count>6,'fixture covers selection outside first six');
  if(count>6) {
    for(const view of ['sector','list']) for(const motion of [false,true]) {
      // Selection and assertions share one browser task: no periodic render or
      // ResizeObserver can repair a mismatch before it is observed.
      const immediate=await evaluate(`(() => {
        setMotion(${motion});setView('${view}');
        document.querySelector('#detailX').click();
        const target=allSessions()[6];
        select(sessionKey(target),{scroll:false});
        const tile=tiles.find(t=>t.s && sessionKey(t.s)===sessionKey(target));
        const synced=!!tile && tile.el.getAttribute('aria-selected')==='true' &&
          JSON.stringify(tiles.filter(t=>t.s).map(t=>sessionKey(t.s)))===JSON.stringify(sceneSessions().map(sessionKey));
        setView('sector');
        const r=tile?.el.getBoundingClientRect();
        return {synced,visible:!!r && r.width>0 && r.height>0 && getComputedStyle(tile.el).display!=='none',
          sized:!!tile && tile.canvas.width>1 && tile.canvas.height>1};
      })()`);
      assert.equal(immediate.synced,true,`Immediate mobile tiles: ${view}, motion ${motion}`);
      assert.equal(immediate.visible,true);
      assert.equal(immediate.sized,true,'Immediate sector switch resizes hidden-list canvases');
    }
    ok('Beyond-first-six selection immediately synchronizes mobile tiles in sector/list and paused/animated modes');
  }
  await evaluate('setMotion(false);document.querySelector("#detailX").click();setView("sector")');
  assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'));ok('Mobile sector has no horizontal overflow');
  await screenshot('mobile-live.png');
  const remote=requests.filter(url=>!url.startsWith(base) && !url.startsWith('data:') && url!=='about:blank');
  assert.deepEqual(remote,[]);assert.deepEqual(errors,[]);ok('No external requests or runtime/console errors');
  const receipt={passed:true,url:base,checks,session_count:count,observed_at:new Date().toISOString(),
    provenance:fixture ? 'Synthetic canonical-contract fixture server, not actual provider telemetry; injected transport failure restored.' : 'Real canonical Codex adapter; transport error deliberately injected and restored; no fixture passed as live.',
    screenshot_files:['desktop-live.png','list-details-live.png','mobile-live.png']};
  fs.writeFileSync(path.join(out,'browser-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log(JSON.stringify(receipt,null,2));
}
main().catch(error=>{fs.writeFileSync(path.join(out,'browser-failure.json'),JSON.stringify({passed:false,checks,error:error.message,errors},null,2)+'\n');console.error(error);process.exitCode=1;}).finally(async()=>{
  if(socket)socket.close();
  if(chrome && chrome.pid) {
    chrome.kill('SIGTERM');
    await Promise.race([new Promise(resolve=>chrome.once('exit',resolve)),sleep(3000)]);
    if(chrome.exitCode===null && chrome.signalCode===null)chrome.kill('SIGKILL');
  }
  try{fs.rmSync(profile,{recursive:true,force:true,maxRetries:8,retryDelay:150});}catch{console.error('Owned browser profile cleanup failed');process.exitCode=1;}
});
