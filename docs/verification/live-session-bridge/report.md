# ACC-19 — Live-session bridge verification

## Scope and lineage

Local integration copy of `origin/task/ACC-12-isometric-sector` at `2404a43`,
which includes canonical `origin/main` at `0ac30cc`. Default preview now consumes
the merged read-only Codex adapter. No merge, push, PR write, deployment,
messaging, provider-process mutation, training or cloud generation performed.

The legacy `app/acc` demo package collided with the canonical `acc` package.
It is now `app/demo_support`, used only for explicit labeled fixtures. Live
polling resolves the canonical registry and the trusted adapter manifest; it
never computes a denominator with the demo's provider/model lookup.

## Evidence actually exercised

- Baseline: 117 canonical Python tests; 22 preview Python tests.
- Current: 117 canonical Python tests; 36 preview Python tests; 7 Node policy
  tests; 12 actual Chromium checks. JS syntax and Python compile checks pass;
  staged whitespace checks pass; static added-line security scan is empty.
- Real loopback preview `http://127.0.0.1:8773/`: Codex source readable, source
  version `0.155.0-alpha.9.2`, 50 indexed records returned at the adapter cap.
  This is not a claim of 50 active agents or an exact total. Historical request
  input was present for 49 rows at the first observation; every occupancy
  percentage was unavailable. Route and lifecycle activity are unverified.
- Browser confirms actual live metadata, inert/stationary unknown/stale agents,
  original Iggy decoding, six-scene rendering bound, all rows in plain list,
  historical-input/provenance labels, selected-detail refresh during a simulated
  transport failure, recovery, dynamic reduced motion, mobile overflow and no
  external requests/runtime/console errors. `browser-receipt.json` has timestamps.
- A hung-reader unit test verifies bounded wait and no duplicate queued reads;
  invalid snapshots and exceptions are redacted. Source/session/context times
  age independently; stale/expired readings never become fresh from polling.
- Host, Origin, fetch-site, CSP, static path and non-GET safeguards tested.
  Only whitelisted UI assets are served; request paths/headers are not logged.
- Owned preview PID 2703043 was terminated with SIGTERM and verified exited,
  demonstrating shutdown does not deadlock on the serve_forever thread. The
  replacement local preview was started as owned process PID 2710814.

## Asset defect found by real execution

Inherited `iggy-iso.png` and `iggy-robot-iso.png` returned HTTP 200 but contained
base64 text, not PNG bytes. FFprobe reported invalid signatures/zero dimensions;
Chromium failed to decode them. The initial failing browser receipt is preserved
as `browser-failure-before-asset-decoding.json`.

Lossless local base64 decoding produced the existing original images (82×112 and
75×112), with no art generation/editing/upload. Exact before/after SHA256 and
sizes are in `asset-decoding.json`. HTTP signature/dimension tests and actual
browser decoding now pass. A script rerun leaves already-decoded images intact.

## Independent review

Failed for the frozen staged snapshot submitted as delegation `deleg_471a935e`.
Review diff SHA256: `a5ce9c3ca328474dde74d5387dc31f4f2883b1dc2b930a30d481995a1fcaf33c`.
The review snapshot covers implementation/tests/assets/evidence, not subsequent
prose-only handoff edits. Exact verdict: `code-review-1.json`; initial receipts
and screenshots are preserved Library-only under
`/home/jimmy/Library of Alexandria/AI Command Center/research/2026-10-01-live-session-bridge/`.

The initial 12 browser checks did run and pass, but they are insufficient proof:
list details were hidden inside the sector container and the harness inspected
hidden textContent. The earlier visible-details claim is withdrawn. Independent
in-memory probes found seven blocking defects: numeric overflow and missing
serialization isolation, unknown validated context time admitting occupancy,
unbounded fetch/body waits, frozen displayed cached ages, hidden list details,
unsynchronized selected mobile tiles, and unreaped retired provider futures.

Fix cycle 1 was delegated to a separate implementation context as
`deleg_84dccb2c`, with deterministic RED/GREEN regressions required for each
finding. No verified commit is allowed until parent verification and a fresh
independent review pass. Initial evidence is not overwritten or passed off as
proof of repaired behavior.

## Parent verification after fixes — 2026-10-02 UTC

The first fix-agent summary was incorrect: retirement cleanup was not implemented.
Parent rerun found 41 preview tests with 2 retirement failures, while 117 canonical
and 17 Node tests passed. The missing cleanup was fixed in cycle 2
(`deleg_151637a5`), preserving the original failing regressions and adding tests
for synchronous completion and failed-completion reference release.

Parent reran the corrected snapshot:
- `python -m unittest discover -s app/tests -p 'test_*.py'`: 43 passed.
- `python -m unittest discover -s tests -p 'test_*.py'`: 117 passed,
  including four read-only local-source integration tests.
- `node --test app/tests/*.test.cjs`: 17 passed.
- `node --check` for app.js, telemetry.js and browser-live.cjs; Python compile
  and whitespace checks: passed. `python scripts/build_zipapp.py`: built.
- Isolated fixture browser: 13 checks passed, eight synthetic records. Receipt
  and synthetic screenshots: `fix-cycle-1/parent-final/`. This is not live proof.
- Fresh corrected-backend server with actual Codex adapter: 13 browser checks
  passed, 50 indexed records at cap. Explicit visible geometry assertions prove
  list details, and immediate mobile selection is checked before any timer can
  repair it. Server was ephemeral and shut down after verification. Its receipt
  and real-session screenshots are Library-only:
  `/home/jimmy/Library of Alexandria/AI Command Center/research/2026-10-02-live-session-bridge/parent-final-live/`.

GitHub API reports this repository **public**, contradicting the older Library
label. No visibility change or push is authorized implicitly. Real-session
screenshots and the local source summary are excluded from Git; the original
assets and labeled synthetic browser evidence may be versioned. Local commit
remains gated on fresh independent review; no merge or deployment is implied.

## Final independent verdict — 2026-10-02 UTC

Fresh independent review `deleg_1e8c9c81` passed; exact verdict is
`code-review-2.json`. All seven original findings were resolved, with no blocking
security or logic findings. Reviewer parsed 50 sections and validated 64 hunks
against frozen text SHA256
`88b99039e5cade250b36ca5fdb0c26d3d9d2ab8165ca2ef9673824ea9d846965`.
Parent confirmed the reviewed index unchanged before adding this verdict and
prose-only final handoff. Reviewer independently ran 43 preview Python and 17 Node
tests, plus 113 canonical tests with the live integration class skipped in an
isolated HOME. Parent's separate 117-test canonical run included the four local
source integration checks.

One nonblocking test-coverage suggestion remains: `test_server.py` exercises an
escaping symlink using a non-whitelisted path, so rejection happens before the
containment guard. Production containment is present; no source change was
made after review. This suggestion is retained for a separate follow-up.

Commit is local-only. Remote publication remains held pending Jimmy's privacy
choice; no PR, merge, repository-visibility change or deployment is authorized.

## Limits / acceptance not implied

Only the merged Codex adapter is enabled. Unmerged Hermes/Claude provider PRs
and their owners/claims remain untouched. This is a live read of a historical
session index, not proof that these workers are running; tool feed, current
occupancy, provider route and active lifecycle are deliberately unavailable.

The original isometric art/layout remains a prototype pending operator visual
approval; mobile close-ups retain inherited camera/cropping behavior. A local
monospace fallback replaces the external Google font. The human-character
ACC-18 companion remains separately committed, not silently substituted for
Iggy. Full ACC-12/13 acceptance, observer chat, specialist feed, configuration,
credentials, canonical integration and any public deployment remain open.
