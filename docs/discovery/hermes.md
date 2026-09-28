# ACC-02 — Hermes telemetry verification

**Task:** ACC-02 (instance of ACC-PV, provider: `hermes`)
**Performed:** 2026-09-28, 07:35–07:45 UTC
**Host:** Jimmy's workstation, Linux. Everything below was read locally; nothing was sent anywhere.
**Repo revision at time of work:** `53d8bcc` (main, after PR #1 merged the `5c9c537` plan restructure)

This is a **discovery** document. No adapter was written and no integration is claimed.

## Summary for the impatient

| Field the dashboard wants | Available? | Source |
| --- | --- | --- |
| Provider installed + version | **yes**, exact | `gateway.sock` `identify`, or `gateway_state.json` |
| Daemon liveness / health | **yes**, exact + timestamped | `gateway.sock` `status` |
| Session identity, model, activity | **yes**, for all 24 persisted sessions | `state.db` → `sessions` |
| Cumulative token usage | **yes**, exact | `state.db` → `sessions`, `session_model_usage` |
| **Context occupancy (tokens in the window now)** | **NO — not reachable read-only** | live in-process only; see [Context occupancy](#context-occupancy-the-important-negative-result) |
| **Context limit (the denominator)** | **partially**, and the obvious source is wrong | `context_length_cache.yaml`; see [The denominator](#the-denominator-and-a-trap-worth-4x) |
| Which session is live *by identity* | **no**, only a count | inferable, not authoritative |

**The headline:** Hermes exposes plenty of *cumulative* usage and zero *context occupancy* to an outside reader. A context-usage gauge for Hermes cannot be honestly built on what a read-only adapter can currently see. ACC-05/ACC-12 should plan for an explicit `unavailable` state for Hermes context, not a percentage.

Encouragingly, Hermes' own internals enforce exactly the guardrail this project committed to — see [What Hermes itself does](#what-hermes-itself-does-worth-copying).

## Installed version and source paths

Hermes **0.21.5**, code sha `d0288be5b3330d2442e3907185b8e9d0958297bb`, supervised by systemd.

| What | Path |
| --- | --- |
| Launcher on `PATH` | `/home/jimmy/.local/bin/hermes` → `~/.hermes/hermes-agent/.hermes/bin/hermes` |
| State/home (`HERMES_HOME`) | `/home/jimmy/.hermes` |
| Installed source (readable Python) | `/home/jimmy/.hermes/hermes-agent` |
| Session store | `~/.hermes/state.db` (SQLite, WAL, schema_version **30**) |
| Control socket | `~/.hermes/gateway.sock` (AF_UNIX) |

Version is obtainable **without executing Hermes** — both the socket and `gateway_state.json` report `code_version`. The adapter never needs to shell out to the CLI.

## Reproducible read-only checks

All five were run for this document. None writes to Hermes state.

**1 — Daemon identity and version (no auth needed; filesystem ACL is the auth boundary):**

```sh
printf '{"verb":"identify","id":1,"protocol":1}\n' | socat - UNIX-CONNECT:/home/jimmy/.hermes/gateway.sock
```

Wire contract, per `gateway/control_socket.py`: **one JSON line in, one line out, server closes.** Protocol version `1`.

**2 — Daemon status:** same as above with `"verb":"status"`.

**3 — Enumerate the supported verbs** (send a nonsense verb; the error lists them):

```sh
printf '{"verb":"__probe__","id":1,"protocol":1}\n' | socat - UNIX-CONNECT:/home/jimmy/.hermes/gateway.sock
```

**4 — Session inventory, read-only, against the live database:**

```sh
sqlite3 "file:/home/jimmy/.hermes/state.db?mode=ro" "select count(*) from sessions;"
```

Verified: `mode=ro` succeeds against the live WAL database while the gateway is running, and returns the same row count as an offline copy.

> **Use `mode=ro`, never `immutable=1`.** `immutable=1` also returns a plausible answer, but it tells SQLite to ignore the `-wal` file, so it silently serves data that predates every uncommitted write. On a database Hermes is actively writing, that is a stale-read generator. It happened to agree here (24 rows) only because the relevant writes had already checkpointed.

**5 — Limit cache:** `cat ~/.hermes/context_length_cache.yaml` (6 lines, 5 entries).

A probe script for checks 1–3 in pure Python (no `socat` dependency) is at the end of this document.

## Session identity, activity and model

`state.db` → `sessions` (24 rows) is the inventory. Useful columns, verified populated:

- **Identity:** `id` (e.g. `20260927_235225_a2512c` — timestamp + short hash), `source`, `session_key`, `parent_session_id` (subagent lineage), `profile_name`.
- **Activity:** `started_at`, `ended_at`, `end_reason`, `last_activity_at`, `message_count`, `tool_call_count`, `api_call_count`.
- **Model routing:** `model`, `billing_provider`, `billing_base_url`, `billing_mode`.
- **Workspace:** `cwd`, `git_branch`, `git_repo_root`.

`source` partitions cleanly — useful as a dashboard facet:

| `source` | sessions |
| --- | --- |
| `cli` | 12 |
| `telegram` | 4 |
| `subagent` | 3 |
| `acp` | 2 |
| `buzz` | 2 |
| `desktop` | 1 |

### Caveats found

- **`last_activity_provenance` is `unknown` for 23 of 24 sessions** (the 24th says `agent.compression`). Treat `last_activity_description` as unreliable; use the `last_activity_at` **timestamp**, which is populated for all 24.
- **`runtime/active_sessions.json` is `{"entries": []}` while the gateway reports `active_agents: 1`.** Re-checked 8 minutes apart, same result. Do **not** use `active_sessions.json` to determine what is live — it reads as empty even with an agent running.
- Consequently **live-session identity is inferential, not authoritative.** Best available heuristic: `ended_at IS NULL` ordered by `last_activity_at DESC`, cross-checked against the `active_agents` count. In this sample that correctly singles out the open `telegram` session (activity `07:36:13`, gateway heartbeat `07:44:02`) — but it is an inference, and the dashboard should not present it as certainty.
- `sessions.title` and `display_name` can contain user-authored text. Excluded from this document and out of scope for the adapter.

## Cumulative usage (available and exact)

Per-session totals live on `sessions`; a per-model/per-task breakdown lives in `session_model_usage` (40 rows). Both split tokens into `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, and carry `estimated_cost_usd` / `actual_cost_usd` with a `cost_status` + `cost_source` provenance pair.

`session_model_usage.task` separates internal overhead from user-facing work — observed values: `''` (main), `background_review`, `approval`, `title_generation`, `compression`. Worth surfacing; it explains token burn users otherwise can't account for.

**These numbers are lifetime throughput and must never be rendered as context fullness.** The scale makes the trap obvious: the busiest session shows `cache_read_tokens` of **28,667,392** against a **272,000**-token window — 105× the window. The reference mockup's headline "TOKEN BURN RATE / MIN" is this family of number, which is exactly why ACC-05 already lists it as a non-goal.

## Context occupancy — the important negative result

**A read-only adapter cannot currently obtain Hermes context occupancy.** Three routes were checked and all three close.

**Route 1 — `messages.token_count`: column exists, never populated.**

The `messages` table (1,962 rows) has a `token_count INTEGER` column and an `active` flag, which looks ideal: occupancy would be `sum(token_count) where active=1`. It does not work:

| total rows | `token_count IS NULL` | `> 0` |
| --- | --- | --- |
| 1962 | **1962** | 0 |

Every row is NULL. The *composition* of the window is tracked (`active=1`: 1,195 rows; `compacted=1`: 597; `_compressed_summary=1`: 4) — Hermes knows **which** messages are live, just not how many tokens each costs. Summing them would require re-tokenizing message content, which needs a tokenizer and would mean reading conversation text — barred by this task's guardrail and by AGENTS.md.

**Route 2 — the control socket: no such verb.** The complete supported set, read live from the server:

```
identify, migrate-profile-identity, pause-for-update, purge-profile-identity,
reload-plugins, rescan-profiles, serve-profile, status, unserve-profile
```

`identify` and `status` are the only read-only members. The other seven mutate gateway state (`pause-for-update`, `reload-plugins`, …) and **must be treated as forbidden** by the adapter. Neither read verb carries per-session context data.

**Route 3 — the internal RPC that does have it, is not reachable.** `tui_gateway/methods_session.py` implements `session.context_breakdown`, returning exactly the right shape:

```
context_used, context_max, context_percent, context_source, context_estimated, categories[], model
```

But `agent/context_breakdown.py:105` shows the values are read off a **live in-memory agent's compressor object** (`compressor.last_prompt_tokens`, `compressor.context_length`). They are computed per-turn and never persisted to `state.db`. `tui_gateway` serves the TUI/Desktop client, which obtains them by *being* the process hosting the agent. Reaching it from outside would mean spawning a Hermes client process and attaching to a live agent — not a read-only observation, and beyond what the plan authorizes.

There is also a full local HTTP API in the tree (`hermes_cli/web_routers/`, with `/api/sessions`, `/api/sessions/{id}`, `/api/sessions/stats`, plus `analytics.py` and `dashboard_ui.py`) whose handlers already take a `read_only` flag. **It is not running:** no Hermes HTTP listener was present (`ss -ltnp` showed only pid 1119's unix socket for Hermes).

**And it would not help anyway** — see the correction at the foot of this document. The HTTP API exposes `context_window` (the *limit*) and no occupancy field at all:

```sh
grep -rnE 'context_(used|percent|max|source|estimated)' hermes_cli/web_routers/   # 0 matches
```

So Route 3 closes on its own merits, not merely because a server is stopped. `tui_gateway` remains the only surface carrying occupancy.

> Note for whoever inspects ports: **127.0.0.1:18789 is `openclaw`, not Hermes** (pid 1120, `/usr/lib/node_modules/openclaw/dist/index.js gateway --port 18789`). It sits next to Hermes' pid 1119 and is easy to misattribute. Hermes binds no TCP port at all.

### Consequence for the dashboard

For Hermes, context occupancy must render as **unavailable with a reason**, per ACC-PA's rule that unsupported metrics never get a fabricated substitute. Do not silently swap in cumulative tokens; as shown above that would read 105× over capacity.

If occupancy for Hermes is later judged essential, it is a **separate scoped task**. The only real options are an upstream change (persist `last_prompt_tokens`, or populate `messages.token_count`) or making the dashboard a `tui_gateway` client, which means hosting/attaching to agent processes rather than observing them. Running the shipped HTTP API is **not** an option — it carries no occupancy field. It should not be smuggled into an adapter task.

## The denominator, and a trap worth 4×

`~/.hermes/context_length_cache.yaml` is Hermes' **observed** limit cache, keyed `model@base_url`:

```yaml
context_lengths:
  gemma4:26b@http://127.0.0.1:11434/v1: 262144
  poolside/laguna-xs-2.1:free@https://inference-api.nousresearch.com/v1: 262144
  gpt-6-luna@https://chatgpt.com/backend-api/codex: 272000
  gpt-6-sol@https://chatgpt.com/backend-api/codex: 272000
  gpt-5.6-luna@https://chatgpt.com/backend-api/codex: 272000
```

**ACC-08 must key the limit registry on `(model, base_url)`, not on model name.** Evidence: `models_dev_cache.json` (4.9 MB models.dev mirror) lists `gpt-6-luna` under 11 providers — `openai`, `azure`, `github-copilot`, `302ai`, … — and **all 11 agree on `context: 1050000`**. The limit actually observed on the route Hermes uses is **272,000**.

So this is not a "pick the right provider" problem; models.dev is internally consistent and still wrong for this route, because the Codex subscription endpoint serves a smaller window than the bare model's. A registry that resolved `gpt-6-luna` by name would compute a **3.86× too large denominator**: a genuinely alarming 200,000-token context would display as **19%** instead of **74%**.

**Ordering ACC-08 should adopt:** observed `context_length_cache.yaml` entry for the exact `(model, base_url)` → else an explicitly curated limit → else **unknown, and no percentage rendered**. models.dev is acceptable as a last-resort *hint* only if labelled as unverified, never as the silent default.

### Two more sharp edges

**1. Trailing-slash endpoint variants.** `session_model_usage` contains both `https://chatgpt.com/backend-api/codex` and `https://chatgpt.com/backend-api/codex/` — the slashed form is used for the `approval`, `title_generation` and `compression` tasks. The cache only holds the unslashed key, so a literal string join misses those rows. Normalize the base URL (strip the trailing slash) before lookup.

**2. The cache covers 5 keys; more models than that are in use.** Models seen in `session_model_usage`, exactly as Hermes stores them:

| model (verbatim) | billing_provider | billing_base_url | in limit cache? |
| --- | --- | --- | --- |
| `gpt-6-luna` | `openai-codex` | `https://chatgpt.com/backend-api/codex` | **yes** — 272000 |
| `gpt-6-sol` | `openai-codex` | `https://chatgpt.com/backend-api/codex` | **yes** — 272000 |
| `gpt-5.6-luna` | `openai-codex` | `https://chatgpt.com/backend-api/codex` | **yes** — 272000 |
| `gemma4:26b` | `custom` | `http://127.0.0.1:11434/v1` | **yes** — 262144 |
| `gpt-5.4-mini` | `openai-codex` | `https://chatgpt.com/backend-api/codex` | **no** |
| `gpt-4o-mini` | `copilot-acp` | `acp://copilot` | **no** |
| `claude-fable-5-1` | `anthropic` | `https://api.anthropic.com` | **no** |
| `deepseek-ai/DeepSeek-V4.1-Flash` | `huggingface` | `https://router.huggingface.co/v1` | **no** |
| `gemma-4-EFB-it-GGUF` | *(empty)* | *(empty)* | **no** |
| `gemma-4-e4b` | *(empty)* | *(empty)* | **no** |

Note `acp://copilot` — a **non-HTTP scheme**; a registry that assumes `https://` keys will mishandle it. And three models carry **empty** `billing_provider`/`billing_base_url`, so `(model, base_url)` is not always fully populated: the registry needs a defined fallback that resolves to *unknown*, not to a guess.

The cache is populated opportunistically as Hermes observes limits, so **absence is normal and will keep happening.** `unknown limit` is a permanent supported state, not a startup gap to wait out.

## What Hermes itself does (worth copying)

`agent/context_breakdown.py:105-114` is short and aligns with this project's guardrails:

```python
def context_usage_fields(compressor: Any) -> Dict[str, Any]:
    """Current occupancy only; lifetime throughput is never a context fallback."""
    used = max(0, getattr(compressor, "last_prompt_tokens", 0) or 0)
    maximum = getattr(compressor, "context_length", 0) or 0
    if not used or not maximum:
        return {}
    source = context_display_source(compressor)
    return {"context_used": used, "context_max": maximum,
            "context_percent": max(0, min(100, round(used / maximum * 100))),
            "context_source": source, "context_estimated": source != "provider_usage"}
```

Three things to carry into ACC-08's contract:

1. **Missing numerator or denominator returns `{}`** — no zero, no guess. An absent limit suppresses the whole metric rather than producing a fake percentage.
2. **Occupancy carries provenance:** `context_source` is `provider_usage` (the provider's own token count) or `local_estimate` (Hermes' rough `chars/4`). The CLI renders the estimated case with a literal `~` marker. Our contract should carry the same distinction — an estimated 74% and a provider-confirmed 74% are not equivalent claims, and the UI should say which it has.
3. The docstring "*lifetime throughput is never a context fallback*" is the same rule this plan set independently. Good sign for the provider contract.

## Smallest safe adapter surface

For **ACC-09**, two reads. Nothing else.

**A. `gateway.sock`, verbs `identify` and `status` only** — provider liveness, version, platform connectivity, `active_agents` count. Both are timestamped (`answered_at`, `updated_at`), which gives the freshness/stale signal directly. One line in, one line out, 2 s timeout, no credentials.

**B. `state.db` opened `file:…?mode=ro`** — `sessions` and `session_model_usage` only.

Column allowlist (everything else, including all free text, stays unread):

```
sessions: id, source, session_key, parent_session_id, profile_name,
          model, billing_provider, billing_base_url, billing_mode,
          started_at, ended_at, end_reason, last_activity_at,
          message_count, tool_call_count, api_call_count,
          input_tokens, output_tokens, cache_read_tokens,
          cache_write_tokens, reasoning_tokens
session_model_usage: session_id, model, billing_provider, billing_base_url,
          billing_mode, task, api_call_count, input_tokens, output_tokens,
          cache_read_tokens, cache_write_tokens, reasoning_tokens,
          first_seen, last_seen
```

**Explicitly out of bounds:**

- `~/.hermes/.env`, `auth.json`, `credentials/`, `install_id` — **not opened during this task**, and never by the adapter.
- `messages` table — conversation content. Also pointless: its `token_count` is NULL.
- `system_prompts` table (20 rows of full prompt text) — prompt content.
- `sessions.title`, `display_name`, `last_activity_description` — user-authored text; `provenance` is `unknown` anyway.
- `~/.hermes/sessions/request_dump_*.json` — 23 debug dumps, 79–128 KB each, containing full request payloads i.e. prompts. Not read here beyond the directory listing. They *would* reveal true context size, which makes them tempting; they are prompt content and occasional debug artifacts, so they are not a telemetry source.
- The seven mutating control verbs.
- Writes of any kind, and `immutable=1`.

**Failure modes ACC-09 must test** (all reachable locally): gateway down → socket refuses, fall back to DB-only with liveness `unknown`; `state.db` absent/locked; `mode=ro` attempted on a checkpointing WAL; limit cache missing the `(model, base_url)` key; empty `billing_base_url`; `acp://` scheme; trailing-slash endpoint variant; `active_agents > 0` with no identifiable open session.

## Acceptance mapping

| ACC-PV requirement | Result |
| --- | --- |
| Installed version, source path/API, reproducible read-only checks | **Met.** 0.21.5 / sha `d0288be5`; paths tabulated; 5 checks, all re-runnable, all executed. |
| Session identity, activity, model, context tokens, context limit **separately**; occupancy vs cumulative | **Met.** Identity/activity/model/cumulative available and evidenced; occupancy **unavailable** with the reason and the three closed routes; limit partially available with a resolution order. |
| Model identifiers exactly as reported | **Met.** 10 verbatim `(model, provider, base_url)` triples, including the empty-provider and `acp://` cases. |
| Sanitized sample data, field availability, freshness | **Met.** Sample below; `token_count`/`active_sessions.json`/`last_activity_provenance` gaps quantified; freshness via socket `answered_at` + `last_activity_at`. |
| Smallest safe adapter surface; no secrets or conversation content | **Met.** Two reads, explicit column allowlist, explicit exclusion list. No credential file or message body was opened. |

## Sanitized sample

Session ids truncated; `title`, `display_name` and `cwd` omitted deliberately.

```
session_id          source    model         billing_mode           msgs calls cum_io  cum_cache_r  state           last_activity_utc
20260927_235225…    telegram  gpt-6-luna    subscription_included   335   253  771025     28667392  open            2026-09-28 07:36:13
20260928_020215…    subagent  gpt-6-luna    subscription_included    23     7   57241       130048  agent_close     2026-09-28 06:03:18
20260926_202306…    telegram  gpt-6-luna    subscription_included    57    93  746026      9624576  session_switch  2026-09-27 04:46:48
20260926_234608…    telegram  gpt-6-luna    subscription_included    38    17   56982       533504  session_switch  2026-09-27 03:53:24
20260924_161146…    telegram  gemma4:26b    chat_completions         22     0       0            0  session_reset   2026-09-26 12:17:21
20260926_055744…    cli       gpt-5.6-luna  codex_responses          64    68  197622      3440128  cli_close       2026-09-26 12:04:01
```

Note row 5: a session with 22 messages and **0 recorded tokens** — a local-model session whose usage was never accounted. Another reason the UI needs a distinct `unknown` rendering rather than displaying `0`.

Observed `end_reason` values: `agent_close`, `cli_close`, `new_session`, `session_reset`, `session_switch`, and NULL for the 10 still-open rows.

## Probe script

Dependency-free equivalent of checks 1–3. Read-only; sends only `identify`, `status`, and one deliberately invalid verb.

```python
"""Read-only probe of the Hermes gateway control socket. One JSON line in, one out."""
import json, socket

SOCK = "/home/jimmy/.hermes/gateway.sock"

def ask(verb):
    payload = json.dumps({"verb": verb, "id": 1, "protocol": 1}) + "\n"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        s.connect(SOCK)
        s.sendall(payload.encode())
        buf = b""
        while not buf.endswith(b"\n") and len(buf) < 512 * 1024:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode() or "{}")
    finally:
        s.close()

for verb in ("identify", "status", "__probe_unknown__"):
    print(f"### verb={verb}")
    try:
        print(json.dumps(ask(verb), indent=2, sort_keys=True))
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
```

Live `identify` result, 2026-09-28T07:43Z:

```json
{"ok": true, "protocol": 1, "result": {
  "code_version": "0.21.5", "code_sha": "d0288be5b3330d2442e3907185b8e9d0958297bb",
  "kind": "hermes-gateway", "pid": 1119, "profile": "default",
  "served_profiles": ["default"], "supervisor": "systemd",
  "hermes_home": "/home/jimmy/.hermes", "protocol": 1, "start_time": 19510}}
```

`status` additionally returns `gateway_state: "running"`, `active_agents: 1`, `session_store: {"status": "ok"}`, `answered_at`, and a `platforms` map (here: `telegram` `connected`, `buzz` `disconnected`) with per-platform `state`, `updated_at`, `needs_attention` and `error_code` — a ready-made per-platform health row, and the natural freshness source for the dashboard.

## Follow-ups for other tasks

Recorded here, not acted on:

- **ACC-08:** key the limit registry on normalized `(model, base_url)`; observed cache beats models.dev; `unknown` is a first-class result; carry `context_source` provenance; handle `acp://` and empty-provider rows.
- **ACC-05 / ACC-12:** Hermes needs an explicit context-`unavailable` treatment, not a gauge. Cumulative tokens and `session_model_usage.task` are worth showing, clearly labelled as lifetime.
- **ACC-09:** the two-read surface and the failure list above.
- **Separate decision — resolved 2026-09-28, see correction below.** Jimmy confirmed the dashboard is for observing only, which rules out the `tui_gateway`-client route. Hermes context occupancy is accepted as permanently `unavailable` for this dashboard unless Hermes upstream starts persisting it.
- **Housekeeping, unrelated:** local `main` in `/home/jimmy/Projects (jimmy's)/ai-command-center` is still at `cb43af6` while `origin/main` is `53d8bcc`. Left untouched — that worktree belongs to another session. Someone should fast-forward it before it misleads a future claim.

---

## Correction — 2026-09-28, later same day

Appended rather than edited in place, per the repository's append-only evidence rule. The body above has been amended at the two points this correction affects; this entry records what was wrong and why.

**What the first version of this document implied:** that running Hermes' shipped local HTTP API (`hermes_cli/web_routers/`) was one of the live options for obtaining context occupancy, pending an authorization decision about starting a server.

**That was wrong, and it was asserted without checking.** The api-server's absence was verified; its *capability* was not. Verified afterwards:

```sh
grep -rnE 'context_(used|percent|max|source|estimated)' hermes_cli/web_routers/
# 0 matches
grep -rn 'context_window' hermes_cli/web_routers/
# hermes_cli/web_routers/models.py:38   _CAPABILITY_FIELDS = (..., "context_window", ...)
# hermes_cli/web_routers/analytics.py:215  "context_window": mc.context_window,
```

The HTTP API carries `context_window` — the **denominator** (a model capability) — and no occupancy field whatsoever. Starting the api-server would therefore yield nothing new for this metric. It remains a possible source for *limits*, which is mildly useful to ACC-08, but it is not a route to occupancy.

**Corrected option set** for Hermes occupancy, if ever pursued:

1. **Upstream change** — Hermes persists `last_prompt_tokens` per turn, or populates `messages.token_count`. Then a read-only adapter gets occupancy for free. Not under this project's control.
2. **Become a `tui_gateway` client** — technically possible, but it means hosting or attaching to Hermes agent processes, i.e. operating Hermes rather than observing it.
3. **Accept `unavailable`.**

**Decision, from Jimmy, 2026-09-28:** the dashboard is for **observing**, not operating. That eliminates option 2 on scope grounds. Option 1 is not ours to make. **Hermes context occupancy is therefore accepted as `unavailable`**, and the dashboard must render it as such with a reason.

This does not weaken the rest of the document. Everything still available for Hermes — liveness, version, per-platform health, session identity, activity, model routing, cumulative usage with its `task` breakdown, and the context **limit** — is unaffected, as is the ACC-08 denominator finding, which matters more for the providers that *can* report occupancy.

**Note for ACC-03 and ACC-PV-codex:** do not generalise this result. Hermes not exposing occupancy says nothing about Claude Code or Codex, which are separate products with their own stores. The context-window gauge may well be honest for them. Verify each independently — and check *capability*, not just whether a server happens to be running.

---

## Addendum — 2026-09-28: observable context *pressure*, and a mislabelled field

Added after the correction above, prompted by Jimmy asking what the dashboard should show in place of a Hermes context gauge. Two findings, both verified.

### `sessions.message_count` is the live-window count, not a lifetime total

It counts messages **currently in the context window**. It goes **down** when Hermes compacts. Observed directly, ~40 minutes apart, on the same open session:

| | 07:40 UTC | 08:20 UTC |
| --- | --- | --- |
| `message_count` | 335 | **125** |
| messages with `compacted=1` | 243 | **561** |

Verified across the whole store — `message_count` equals the `active=1` count for **26 of 26 sessions, zero exceptions**, while equalling the *total* row count for only 21 (the five compacted sessions are where they diverge):

```sh
sqlite3 "file:/home/jimmy/.hermes/state.db?mode=ro" "
with c as (select s.id, s.message_count mc,
  (select count(*) from messages m where m.session_id=s.id and m.active=1) act,
  (select count(*) from messages m where m.session_id=s.id) tot from sessions s)
select sum(mc=act) matches_active, sum(mc=tot) matches_total, sum(mc<>act) differs, count(*) n from c;"
# 26 | 21 | 0 | 26
```

**ACC-09 must not label this field "total messages" or "messages exchanged".** It is `messages_in_window`. A UI showing it as a session total will silently shrink a long conversation every time Hermes compacts, which looks like data loss.

The lifetime count is `select count(*) from messages where session_id = ?`, or `api_call_count` for turns.

### Context pressure is observable even though occupancy is not

Compaction leaves a durable trail. Sample (live, read-only):

```
source / model            in window   folded away   summaries   state
telegram / gpt-6-luna           125           561           2   open
telegram / gpt-6-luna            57           214           1   ended
cli / gpt-5.6-luna               64            99           1   ended
cli / gpt-5.6-luna               42            41           1   ended
cli / gpt-6-sol                 236             0           0   ended
cli / gpt-5.4-mini              160             0           0   ended
```

The last two rows carry more messages than any compacted session and **never compacted once** — while row three compacted repeatedly at a quarter that size. Message count alone therefore predicts nothing about window pressure; the compaction trail does. Folding also has a measurable cost: `session_model_usage` where `task='compression'` shows 3 API calls and 63,007 input tokens.

Available fields: `active=1` count (in window), `compacted=1` count (folded away), `_compressed_summary=1` count (summary artifacts), `rewind_count`, and a set of compression-health columns — `compression_fallback_streak`, `compression_ineffective_count`, `compression_failure_cooldown_until`, `compression_recovery_deadline`, `compression_failure_error`. All five health columns are currently zero/NULL across 26 sessions, i.e. they are **trouble indicators**, dormant in the healthy case, and worth surfacing as an alert rather than a routine readout.

### Decision (Jimmy, 2026-09-28): a context pressure strip replaces the gauge

The Hermes context slot shows messages in window, messages folded away, summary count, and the window size (272,000 for the Codex-routed models, which *is* known) as honest context.

**Two hard constraints on rendering it:**

1. **Numbers and events, never a fill bar.** Compaction count says the window *has* overflowed N times; it says nothing about how full it is now — immediately after a compaction it is nearly empty. Anything bar- or dial-shaped implies a fullness reading that does not exist. This is a proxy for pressure and history, not a substitute for occupancy.
2. **The card states that occupancy is unavailable**, with the reason, rather than letting the pressure strip imply the gauge was satisfied.

This is design input for **ACC-05**, recorded here because the evidence lives here. ACC-05 owns the actual screen definition; this task does not design it.

Separately, Jimmy noted that making the dashboard an operable client for agents is a **future major feature in its own right**, not a sub-task of any adapter. The observe-only constraint in the plan's Guardrails stands for this release.
