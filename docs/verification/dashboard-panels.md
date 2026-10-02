# Verification — dashboard panels (ACC-12)

Date: 2026-09-29. Branch: `task/ACC-12-dashboard-panels`.
Revision: see commit "ACC-12: dashboard panels over the shared telemetry contract".

## Checks run

- `python3 -m unittest discover -s app/tests` — **22/22 pass** (13
  contract + 9 server smoke), ~4s.
- `node --check app/ui/app.js` — syntax OK.
- Live smoke, demo mode (`python3 app/server.py --demo --port 8471`):
  - `GET /api/health` → `{"ok": true, "mode": "demo", "providers": ["Claude Code", "Codex", "Hermes"]}`
  - `GET /api/sessions` → 3 providers; Hermes sessions show `percent_used`
    21/4 with `freshness: fresh`; `cc-parent` is `stale`; `cc-child-3`
    (unknown model) has `percent_used: null` + `unavailable_reason`;
    Codex `ok: false` with the sqlite-lock error and zero sessions.
  - `GET /` → 200, dashboard HTML; `GET /ui/app.js` → 200.
  - Activity tools across sessions order newest-first.
  - `POST /api/sessions` → 501 (read-only by construction).
- Live smoke, live mode (no `--demo`): `/api/sessions` returns
  `"mode": "live", "providers": []` — honest empty, no demo fallback.
- Server binds `127.0.0.1` explicitly (verified in test
  `test_binds_loopback_only` and in `server.py`).

## Acceptance coverage (ACC-12)

- Source, session identity, status, context metrics, freshness and
  readable error/unavailable states: rendered from `/api/sessions`
  (board, list, detail strip). Unknown limits show used tokens with no
  percentage and an explicit reason.
- Demo vs live: `mode` in the payload; demo shows the persistent SAMPLE
  DATA banner; live-with-no-adapters shows "no providers connected".
  Never a silent fallback.
- Keyboard (1/2/r/Esc/arrows/Enter), `prefers-reduced-motion` + motion
  toggle, narrow-window collapse to list, long-name truncation via
  `title`: implemented per the approved ACC-05 design; verified by code
  inspection (same handlers as the approved mockup).
- Untrusted text renders inert: `app.js` builds DOM with `textContent`
  only — no `innerHTML` with API strings; server JSON-escapes strings.

## Not verified here

- **Screenshots**: no browser on this machine can render the page
  (local `file://` crashes the managed browser; `muse.ai` hosting is
  network-blocked). The UI is a direct evolution of the ACC-05 mockup
  Jimmy approved via interactive widget preview.
- **Real adapters**: ACC-09/10/PA-codex need provider discovery
  (ACC-02/03/PV-codex) on Jimmy's machine. The registry seam is proven
  by the dummy-provider contract test instead.
- **Long-session soak**: bounded polling (single thread, no overlap,
  per-adapter timeout) is implemented and unit-tested; an extended soak
  run was not performed.
