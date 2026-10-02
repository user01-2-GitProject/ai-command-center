# AI Command Center — app

Local-first, read-only dashboard. Python 3 standard library only — no
dependencies to install.

## Run

```sh
# from the repository root
python3 app/server.py
# → http://127.0.0.1:8471  (loopback only)
```

```sh
# demo mode: labeled sample fixtures, SAMPLE DATA banner
python3 app/server.py --demo
# or: ACC_DEMO=1 python3 app/server.py
```

Live mode loads only the reviewed, merged adapters in `acc/providers/manifest.py`
(currently Codex). It reads allowlisted session metadata, not prompts, titles,
credentials or conversations. The source can be readable while activity and
context occupancy remain unknown. Codex last-request input is historical, never
an occupancy percentage. An explicitly empty registry remains an honest empty
state; errors never switch to fixtures. Unmerged Hermes/Claude provider PRs are
not enabled by this slice.

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `ACC_PORT` / `--port` | 8471 | listen port (host is always 127.0.0.1) |
| `ACC_DEMO` / `--demo` | off | register labeled demo fixtures |
| `ACC_POLL_SEC` | 15 | adapter poll interval |
| `ACC_ADAPTER_TIMEOUT_SEC` | 10 | per-adapter read timeout |

Canonical live freshness is classified independently per source/session/context:
fresh through 30 seconds, stale through 300 seconds, then expired. Missing,
nonfinite and future times are unknown. Polling never resets event timestamps.

## Test

```sh
python3 -m unittest discover -s tests       # canonical core/provider tests
python3 -m unittest discover -s app/tests   # preview, live bridge and HTTP tests
node --test app/tests/telemetry.test.cjs     # consumer aging/motion policy
node --check app/ui/app.js                  # dashboard js syntax
```

## Layout

- `app/server.py` — loopback-only HTTP server: `/` (UI), `/api/sessions`,
  `/api/health`. Canonical loopback Host/Origin/CSP guards apply. POST returns
  405; other mutation methods are unsupported. `/api/health` is shell health,
  not proof of provider health or active work.
- `app/demo_support/` — legacy demo-only model (`model.py`), provider
  + limit registries (`registry.py`), adapter interface (`adapters.py`),
  poller with timeout isolation (`poller.py`), labeled demo fixtures
  (`demo.py`).
- `app/ui/` — static dashboard: `index.html`, `style.css`, `app.js`.
  No build step. Fetches `/api/sessions`; inserts all provider text as
  text, never HTML.
- `app/tests/` — contract tests and server smoke tests.

## Live bridge and verified preview scope (ACC-19)

- `app/live_sessions.py` consumes canonical `acc.models` and `acc.registry`.
  It does not define a context limit or use the legacy demo limit lookup.
  Only trusted `acc/providers/manifest.py` controls live adapter registration.
- `app/demo_support/` replaces the old conflicting `app/acc/` namespace;
  its model/registries are fixtures only, never a live provider contract.
- Source observations, session events and context events age independently.
  Connection failure retains explicitly stale last-known metadata, clears
  occupancy/activity claims and updates selected details. Reconnect reads
  actual sources again, without restarting or opening provider sessions.
- One daemon reader per in-flight source, bounded batch wait, skipped
  overlapping polls. A hung reader cannot be killed by Python, but is not
  enqueued again and cannot block interpreter shutdown. No provider processes
  are spawned. Cache is RAM only; no private content or provider route leaves
  the backend.
- At most six sessions appear in canvas/mobile tiles; every returned session
  remains in the plain list. Session selection uses provider-qualified keys.
  A source-cap badge means the total is unknown, not exactly 50 sessions.
- Agent motion requires a fresh explicit busy state. Iggy is decorative and
  is not a worker-status assertion; reduced motion, pause and hidden tabs stop
  animation. The browser aging policy also stops stale cached activity.
- No remote fonts/resources are requested. The system monospace fallback is
  used pending a locally bundled art-direction font. Unknown gauges are empty,
  not an apparent 100% load; last-request input is an explicitly historical
  number, with its own age classification.
- The inherited Iggy PNG paths held base64 text. Their exact underlying PNGs
  were decoded, not regenerated or edited. Provenance/hashes are in
  `docs/verification/live-session-bridge/asset-decoding.json`; the repair script
  is idempotent. Mechanical HTTP 200 is not proof an image decodes.

Real-browser QA (Node 22+ and Chromium required for testing, neither for runtime):

```sh
python3 app/server.py --port 8773
# second terminal, repo root, real local Codex metadata:
ACC_QA_URL=http://127.0.0.1:8773 node app/tests/browser-live.cjs
```

This test uses a fresh temporary Chromium profile, records only minimal metadata
summary/screenshots, and deliberately injects/restores a transport failure. It
never uses personal cookies or substitutes a fixture for the live-source check.
The live test requires actual indexed sessions; offline/empty cases are unit
tested rather than passed off as live integration. Results in
`docs/verification/live-session-bridge/`.

Not acceptance of the full ACC-12/13 dashboard. Operator chat, specialist feed,
configuration/credential UI, remote access, deployment and unmerged provider
adapters remain out of scope. ACC-18's separate Hermes human-character companion
has not been cherry-picked into this newer Iggy design; integration needs the
operator's art/layout decision rather than silently replacing Iggy.
