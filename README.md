# AI Command Center

A local-first dashboard for Jimmy to oversee agent sessions, with trustworthy context-window visibility and a readable 16-bit-inspired interface. Hermes, Claude Code and Codex are the first providers; providers are pluggable by design.

The runnable shell deliberately shows **Not connected**. Provider adapters arrive in later tasks; no demo sessions are represented as live data.

## Start here, agents

1. Read [AGENTS.md](AGENTS.md).
2. Open the canonical work queue: `/home/jimmy/Library of Alexandria/AI Command Center/Plan of Attack.md`.
3. Pick one eligible task, claim it, and execute its [task specification](docs/TASKS.md).
4. Deliver verifiable files and a handoff. Check off only what was actually verified.

Library overview: `/home/jimmy/Library of Alexandria/AI Command Center.md`.
GitHub holds code, technical specifications and test evidence. The Library holds task status, ownership, decisions and handoffs. Do not create a second issue tracker or copy task status into this README.

If you cannot access the Library, use an explicit task assignment from Jimmy/operator, work in an isolated branch, and return the handoff for synchronization. Do not guess ownership or claim the whole project is complete.

## Run locally

Requires Python 3.12 or newer. Create the virtual environment and install the pinned runtime dependency set (currently empty because the shell uses only the standard library):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

Start the dashboard with:

```sh
.venv/bin/python -m acc
```

Open http://127.0.0.1:8765. The server binds to IPv4 loopback only. Stop it with Ctrl+C. To select another local port, set `ACC_PORT` to an integer from 1024 through 65535; the bind address remains fixed at `127.0.0.1`.

## Checks and build

```sh
.venv/bin/python -m compileall -q acc tests scripts
node --check acc/static/app.js
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/build_zipapp.py
```

Run the packaged application with `python3 dist/acc.pyz`. GitHub Actions runs the same compile, test and zipapp build steps on pushes and pull requests.

The service exposes only an empty snapshot and static files. It has no provider connections, message sending, credential handling, telemetry persistence or remote binding. See [the task queue](docs/TASKS.md) and [architecture decision](docs/architecture.md) for the implementation sequence and safety boundaries.

## Reusable assignment

> Work on AI Command Center. Read the repository AGENTS.md and the Library Plan of Attack. Complete one eligible unclaimed task, using the claim procedure and an isolated branch. Deliver its named artifacts, run its acceptance checks, and append a handoff in its Library task note. Mark review when delivered; never mark unverified work done. Do not deploy or message other agents.

For the first connector investigations, assign ACC-02 (Hermes), ACC-03 (Claude Code) and ACC-PV-codex (Codex) to different agents explicitly. Those tasks write separate files and can proceed independently.
