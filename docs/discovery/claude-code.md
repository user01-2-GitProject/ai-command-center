# ACC-03 — Claude Code read-only telemetry

Verified 2026-09-29 by Codex, session `01a0eee3-aec9-7c13-9d8c-ddbc91e91090`.
Base revision `53d8bcc`. Discovery only; no adapter or provider configuration changed.

## Installed version and evidence boundary

- Installed latest binary: `/home/jimmy/.local/share/mise/installs/claude/2.1.283/claude`.
  Running that exact binary with `--version` returned `2.1.283 (Claude Code)`.
  `.../claude/latest/claude` resolves to this version.
- Historical ACC-02 parent transcript reports **2.1.275**, model **`claude-opus-5`**.
  Do not label every stored session with the currently installed CLI version.
- One historical child metadata sample reports **`claude-sonnet-5`**.
  These are verbatim model IDs, not inferred product names or registry limits.
- Initial `claude --version` used the `~/.local/bin/claude` shell wrapper, which
  invoked mise and attempted to resolve/install `latest`. It failed with
  `Read-only file system (os error 30)`. It was not retried with write permission.
  The explicit installed binary above avoided that side effect. Never invoke
  the wrapper during adapter polling.

## Proven read surfaces

| Field | Observed evidence | Meaning and limitation |
| --- | --- | --- |
| Parent identity | `projects/<project>/<sessionId>.jsonl`, top-level `sessionId` | Stored session identity, not proof of activity. |
| Child identity and relationship | `projects/<project>/<parentId>/subagents/agent-<agentId>.jsonl`, `agentId`, `isSidechain` | Sample child's `sessionId` equals the parent filename. Key child identity by parent plus agent ID; do not merge its usage into parent usage. |
| Model | `message.model` on assistant records | Last response's model. May differ between parent and child or change during a session. |
| Response input components | `message.usage.input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` | Last observed API input, not cumulative session usage and not current live occupancy. Never sum repeated response records. |
| Output tokens | `message.usage.output_tokens` | Response output; keep separate from the input measurement. |
| Source time | Record `timestamp` | Last recorded event/measurement time; filesystem mtime is only a read hint. |
| Process registration | `~/.claude/sessions/*.json` | Allowlisted PID, process start, session ID, version, status and timestamps. Exclude names, cwd, sockets, bridge identities, and all adjacent `.key` files from output. |
| Reported activity | Registration `status`, `updatedAt`, `statusUpdatedAt` | Observed `idle` and `busy`; status can survive process exit. Does not itself prove execution. |
| Context limit / percentage | No compatible limit found in sampled transcript metadata or registration fields | **Unavailable**. Do not assume 200k/1M from model name or use another provider's limit. |
| Live task label | Not verified from an approved content-free surface | **Unavailable**; never derive it from prompts, titles or conversation text. |

### Counts and sanitized samples

Metadata-only enumeration found 20 parent and 39 child transcript files across the
local store. Only one selected parent (prior project discovery session) and one
small child were inspected for usage/schema; this is not a store-wide capability claim.
No conversation bodies, prompt text, tool inputs, keys, or account identities were emitted.

Parent sample: 193 assistant records; last event `2026-09-28T08:23:11.676Z`.
Latest usage: input `2`, cache write `28`, cache read `248604`, output `371`.
Last response input = `248634` tokens, explicitly **historical request input**.
No verified denominator: no percentage. The timestamp is the last transcript event,
not asserted as the exact usage-record timestamp.

Child sample: five assistant records; range `2026-09-21T21:37:05.712Z` to
`2026-09-21T21:37:16.659Z`. Latest usage: input `2`, cache write `796`, cache
read `29333`, output `597`; historical response input `30131`. Parent relation
verified by ID equality, not by interpreting its conversation. Sample IDs and
project names omitted. No supported child context denominator was observed.

### Process-state correction and permission limits

There were 15 registration files: 13 reported idle, two busy; ten recorded
version 2.1.281 and five 2.1.275. All 15 PIDs appeared absent inside the execution
sandbox. **That was an isolation artifact, not proof all sessions had stopped.**
A separately permitted host-level read found 13 PIDs absent and two present.
The two present processes had matching `/proc/<pid>/stat` start ticks and an
executable basename `claude`; both registrations reported idle and version 2.1.275.
Neither was an AI Command Center project session. Thus process presence can be
corroborated without issuing a provider command, but working/busy state is not proven.

The recorded `pidDomain` suffix matched the host PID namespace for those two.
An attempted interpretation of its middle identifier as boot ID did **not** match;
that interpretation is unverified and must not enter an adapter. Treat domain as
opaque until its producer semantics are established. A PID/start/executable match
is useful corroboration, not a documented cross-domain identity contract.

If host process metadata is inaccessible, render liveness **unknown**, not offline.
If the process is present but its activity record is old, show last-reported idle
with its timestamp, never a fresh active badge. ACC-06/08 own actual freshness thresholds.

## Documented capability versus accessible capability

The official [status-line documentation](https://code.claude.com/docs/en/statusline)
was read on 2026-09-29. A configured command receives parent context usage and a
limit. Its separate `subagentStatusLine` feed includes per-child `tokenCount`,
`contextWindowSize`, and resolved model. The feeds must not be interchanged.
User settings contain neither configuration; no exported payload was observed.
Installing a callback would change provider configuration and is not this task's
read-only surface. No hook was installed, no process attached, no session started.
This documents a future option, **not a verified working integration**.

The official [subagent documentation](https://code.claude.com/docs/en/sub-agents)
confirms separate child transcripts and compaction boundaries. A compaction event
is historical; its pre-compaction count is not present occupancy. The selected
parent had only `stop_hook_summary` system records, so compaction was not locally
verified on this sample.

## Smallest safe ACC-10 boundary

Read existing registration JSON and explicitly selected transcript metadata.
No CLI, SDK session, socket request, status-line modification, or provider dispatch.
Read JSONL one line at a time inside the adapter boundary; discard message content,
prompts, tools/arguments, attachments, titles, paths and account/bridge fields before
returning anything. The file format mixes private content and metadata: never
copy raw records to logs or browser responses, including malformed-line errors.
Use bounded file/line sizes and polling, isolate per-file errors, and reject
symlinks outside the configured source root. Work from a configured project/session
allowlist; the discovery's aggregate inventory is not permission for arbitrary UI disclosure.

Expose identity, relationship, exact model, last measurement time, and process
corroboration separately. Context occupancy/limit/percentage remain unavailable
for the current source; a separate historical API-input field can carry the values
above if ACC-08 explicitly models that semantic. Unknown is not zero.

Missing source → offline/unavailable reason; denied source → permission denied;
partial final line → skip until complete and retain older timestamp as stale;
malformed record → contained error without raw data; old usage → last-reported
historical value, no current gauge. Parent and child IDs must remain distinct.

## Reproducible checks

Read-only installed-version check:

```sh
/home/jimmy/.local/share/mise/installs/claude/2.1.283/claude --version
```

The following metadata-only Python check can be run on the host. It never opens
`.key` files or emits session names, transcript text, command arguments, environment
variables or identifiers. Inside a PID-isolated sandbox its process counts are not
host liveness evidence.

```python
from pathlib import Path
import collections, json
root = Path.home() / '.claude'
counts = collections.Counter()
for path in (root / 'sessions').glob('*.json'):
    row = json.loads(path.read_text())
    counts['registration'] += 1
    status = row.get('status')
    counts[status if status in ('idle', 'busy') else 'unknown_status'] += 1
    pid = row.get('pid')
    if not isinstance(pid, int) or pid <= 0:
        continue
    proc = Path('/proc') / str(pid)
    if not proc.exists():
        counts['pid_absent_in_observer_namespace'] += 1
        continue
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    counts['start_match' if str(row.get('procStart')) == fields[19]
           else 'start_mismatch'] += 1
print(dict(counts))
parent = next((root / 'projects').glob(
    '*/37ad8fad-7366-46fc-b6a2-0f6e5e4d2a60.jsonl'))
last = None
for line in parent.open():
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    message = row.get('message')
    if row.get('type') != 'assistant' or not isinstance(message, dict):
        continue
    usage = message.get('usage')
    if not isinstance(usage, dict):
        continue
    last = {key: usage[key] for key in (
        'input_tokens', 'cache_creation_input_tokens',
        'cache_read_input_tokens', 'output_tokens')
        if isinstance(usage.get(key), int) and usage[key] >= 0}
print('Historical parent usage:', last)
```

Equivalent checks above were run; `git diff --check` passed. Live context export
and real-time child activity were **not run/not available**. Discovery acceptance
can accept these explicit unavailable fields; ACC-10 must still test its adapter
and record a fresh real metadata read. No provider installed, upgraded, configured,
resumed or dispatched. No credentials were opened.
