# ACC-PV-codex — Codex telemetry discovery

Date: 2026-09-29. Agent: Codex / `01a0eee3-aec9-7c13-9d8c-ddbc91e91090`.
Base: `53d8bcc`. Read-only metadata investigation, not a delivered adapter.

## Version and sources

- Direct installed CLI `/home/jimmy/.local/share/mise/installs/codex/0.157.1/bin/codex --version`
  returned **codex-cli 0.157.1**. It warned that PATH alias creation was denied by
  the read-only sandbox; no elevated rerun or wrapper execution was performed.
- The selected running desktop task's persisted `cli_version` is
  **0.155.0-alpha.9.2**. Installed standalone CLI version is not desktop runtime version.
- Database: `~/.codex/state_5.sqlite`, opened with `mode=ro` and
  `PRAGMA query_only=ON`. Its `threads` table contained 34 records.
- Rollout: `threads.rollout_path` resolves beneath `~/.codex/sessions/`; one
  selected AI Command Center task was inspected. JSONL includes private content:
  only the explicitly allowed metadata below was returned; no response items,
  instructions, tool output, prompt, title, preview, or first-user-message was emitted.
- Exact observed model: **`gpt-6-astra`**; model provider **`openai`**. Route/base URL
  was not read from credentials/config or guessed from these identifiers.

## Field availability

| Field | Verified source | Availability / interpretation |
| --- | --- | --- |
| Session identity | DB `id`, rollout `session_meta.id` | Available. A stored record is historical evidence, not activity proof. |
| Version | DB `cli_version`, rollout `session_meta.cli_version` | Available per session. |
| Model/provider | DB `model`, `model_provider`; `turn_context.model` | Available, exact strings; future adapter must bind the measurement to its turn/model, not only the latest DB model. |
| Lifecycle evidence | `event_msg` payload type `task_started` | Available as last-reported event. Observed start at `2026-09-29T20:39:01.305Z`; no terminal event at sample time. An unclosed start may survive a crash. |
| Live runtime status | Codex app `list_threads` read-only tool | Current selected task returned `active`. This corroborates the sample, but the app tool is not an independently callable backend API. |
| Last reported usage | `event_msg.token_count.info.last_token_usage` | Available separately from total usage. Per-response input/output counts, timestamped; cached input is a subset, not something to add again. |
| Context limit | Same record's `model_context_window`; `task_started.model_context_window` | Both reported **258400** for this task. Treat as observed runtime limit, not a universal model spec. |
| Cumulative usage | DB `tokens_used`; `total_token_usage` | Available but **not occupancy**. Must never become the gauge numerator. |
| Exact current occupancy | No separately identified live occupancy field established | Unavailable as a continuously current measurement. Last-response input can be displayed with that explicit label; its semantics must not be silently promoted to present occupancy. |
| Child relationships | Not verified in this one parent sample | Unavailable pending a bounded child-specific check; do not infer from names. |
| Current task description | Excluded private prompt/title fields | Unavailable through this approved metadata surface. |

## Sanitized observed sample

At `2026-09-29T20:49:07.122Z`, the selected task's `token_count` event reported:

```json
{
  "model": "gpt-6-astra",
  "model_provider": "openai",
  "last_token_usage": {
    "input_tokens": 104334,
    "cached_input_tokens": 103424,
    "cache_write_input_tokens": 0,
    "output_tokens": 350,
    "reasoning_output_tokens": 48,
    "total_tokens": 104684
  },
  "total_token_usage": {
    "input_tokens": 2004640,
    "output_tokens": 14444,
    "total_tokens": 2019084
  },
  "model_context_window": 258400
}
```

The cumulative 2,019,084 total already exceeds the reported window by almost 8x;
that does not mean context overflow. The per-response total is input plus output;
adding cached input or reasoning output again would double count. A current percent
is deliberately not asserted. A future last-response-input/limit display must be
explicitly labelled and model/turn bound, with stale state when later context or
compaction invalidates the reading. The session metadata's `context_window` object
contains a `window_id`, **not a numeric denominator**.

At the sample point there were 26 `token_count` events and 27 separate
`token_usage_record` records. The latter contain `usage`, `thread_token_usage`,
`turn_token_usage`, and correlation IDs. They must not be summed together with
`token_count`; they can describe the same underlying API usage. No private IDs or
reasoning text are needed for the dashboard.

## Runtime interface boundary

Official [App Server documentation](https://learn.chatgpt.com/docs/app-server),
read 2026-09-29, documents `thread/read` without resume, runtime status, loaded
thread listing and usage notifications. The documented interface is distinct from
files on disk. Starting a new server would not establish the existing desktop
server's loaded state. No server was started, no socket attached, and no session
was resumed or subscribed. Access to an existing backend-compatible runtime read
endpoint remains unverified. File adapters must therefore show unknown liveness
or explicitly last-reported activity, even if this discovery's app listing proved
this particular sample active.

Attempted `wait_threads` for the calling task failed with “cannot wait on the
calling thread”; no retry loop. The read-only app listing succeeded instead and
only the selected task's ID/status/kind were emitted, not other task summaries.

## Smallest safe adapter surface

Read-only SQLite index query using a configured project/session allowlist, then
bounded metadata-only streaming of rollout files under the configured sessions
root. Query named columns only; never `SELECT *`. `rollout_path` is an internal
locator and must not reach the browser. Validate resolved path containment and
reject symlinks escaping the root. Keep `archived` separate from runtime status.

Allowed DB fields: id, rollout_path (internal only), created/updated times,
model, model_provider, cli_version, archived. `tokens_used` may be inspected for
comparison but is not a context metric. Allowed rollout paths: session metadata
IDs/version/provider; turn model/correlation; lifecycle event type/time; token
count numeric fields. Explicitly exclude `base_instructions`, `response_item`,
`world_state`, message bodies, titles/previews, account IDs, logs and auth files.

Use `mode=ro`, query timeout and query-only mode; never `immutable=1` on a live WAL
store. Do not copy the DB or checkpoint its WAL. A reader may encounter locked,
missing, partially written or version-changed storage: report a contained source
error/unavailable reason and retain previous values only with old timestamps.
Incomplete final JSONL line should wait for the next poll; malformed complete
lines must never be logged raw. No DB repair, provider restart or automatic resume.

The schema and rollout format are local implementation details, so ACC-PA-codex
must test version/schema drift and bounded reads. ACC-08 owns the model-limit
matching rule; same-event provider-reported limits take priority over generic
name catalogues. Unknown or mismatched model/limit suppresses percentages.

## Reproducible read-only probe

The following exact targeted check was used (output subset; no conversation data):

```python
from pathlib import Path
import json, sqlite3
root = Path.home() / '.codex'
db = sqlite3.connect((root / 'state_5.sqlite').as_uri() + '?mode=ro', uri=True)
db.execute('PRAGMA query_only=ON')
row = db.execute('SELECT rollout_path, cli_version, model, model_provider '
                 'FROM threads WHERE id=?',
                 ('01a0eee3-aec9-7c13-9d8c-ddbc91e91090',)).fetchone()
db.close()
assert row is not None
path = Path(row[0]).resolve()
assert path.is_relative_to((root / 'sessions').resolve())
print('version/model/provider:', row[1:])
last = None
for line in path.open():
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        continue
    payload = record.get('payload', {})
    if record.get('type') != 'event_msg' or not isinstance(payload, dict):
        continue
    if payload.get('type') != 'token_count':
        continue
    info = payload.get('info')
    if not isinstance(info, dict):
        continue
    usage = info.get('last_token_usage')
    if not isinstance(usage, dict):
        continue
    last = {'timestamp': record.get('timestamp'),
            'model_context_window': info.get('model_context_window'),
            'usage': {key: usage.get(key) for key in
                      ('input_tokens', 'cached_input_tokens', 'output_tokens',
                       'reasoning_output_tokens', 'total_tokens')}}
print(last)
```

The live task continues writing its own telemetry, so a later probe's counts and
timestamps will differ; the adapter must not hardcode this snapshot. Database
read, version check, schema inspection, filtered rollout read, and selected app
status were verified. `git diff --check` passed. Fault-injection tests belong to
the adapter task; none are claimed here. No provider state was intentionally
modified, no process dispatched, and no credential file opened.
