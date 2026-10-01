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

Live mode with no adapters registered shows an honest "no providers
connected" state — demo data is never substituted silently. Real provider
adapters land with ACC-09 / ACC-10 / ACC-PA-codex.

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `ACC_PORT` / `--port` | 8471 | listen port (host is always 127.0.0.1) |
| `ACC_DEMO` / `--demo` | off | register labeled demo fixtures |
| `ACC_POLL_SEC` | 15 | adapter poll interval |
| `ACC_ADAPTER_TIMEOUT_SEC` | 10 | per-adapter read timeout |
| `ACC_STALE_AFTER_SEC` | 60 | freshness threshold |

## Test

```sh
python3 -m unittest discover -s app/tests   # 22 tests: contract + server smoke
node --check app/ui/app.js                  # dashboard js syntax
```

## Layout

- `app/server.py` — loopback-only HTTP server: `/` (UI), `/api/sessions`,
  `/api/health`. Read-only; no POST/PUT/DELETE handlers exist.
- `app/acc/` — telemetry contract: normalized model (`model.py`), provider
  + limit registries (`registry.py`), adapter interface (`adapters.py`),
  poller with timeout isolation (`poller.py`), labeled demo fixtures
  (`demo.py`).
- `app/ui/` — static dashboard: `index.html`, `style.css`, `app.js`.
  No build step. Fetches `/api/sessions`; inserts all provider text as
  text, never HTML.
- `app/tests/` — contract tests and server smoke tests.
