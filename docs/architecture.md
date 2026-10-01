# ADR ACC-06: Local metadata service with isolated provider readers

Status: proposed for independent task review. Date: 2026-09-29.
Deciders: Jimmy (product boundaries), assigned reviewer (technical acceptance).

## Context

ACC-01, ACC-02, ACC-03 and ACC-PV-codex were independently accepted as documentation
on 2026-09-29. Evidence: `docs/discovery/prior-work.md`, `claude-code.md`, `codex.md`,
and `docs/discovery/hermes.md` at Git revision `a9ace6c` (published discovery branch).
The newest `docs/completion-plan.md` is the requested phase sequence. It and the
ACC-16/17 task definitions are preserved from the existing design commit `d67da97`;
this imports task scope, not visual approval or the unreviewed prototype.

All three sources support useful historical metadata. None currently establishes
continuously current context occupancy through the approved independent read
surface. The first integration will prove real identity, model, timestamps and
honest unavailable context, not claim the context-visibility requirement is solved.

## Decision

Use Python 3.12+ and its standard library: SQLite read-only queries, JSONL streaming,
Unix sockets, dataclasses, subprocess isolation, unittest, and a small loopback HTTP
server serving static HTML/JS. Python 3.14.7 is installed locally. No third-party
runtime packages; an empty, documented requirements lock records that choice.
Setup creates a venv and installs that lock offline. Start: `.venv/bin/python -m acc`.
Build: a self-contained Python zipapp; startup/shutdown require no daemon/service
installation. Use `127.0.0.1` only. Reject attempts to bind other addresses.

The HTTP server is a single-user local application boundary, not an internet
server. Never expose it through a reverse proxy, tunnel, wildcard binding or CORS.
A framework can replace the small transport when requirements justify it.

### Flow and ownership

1. Trusted local configuration supplies adapter module paths and explicit session
   allowlists. A registry manifest contains module entries; display/provider IDs
   and provider-specific logic live only in each adapter. Shell/UI never branch on
   provider name. Module imports are operator configuration, never telemetry input.
2. A background collector runs each configured reader in a short-lived child
   **of this application**, not a provider agent. Each reader performs only its
   approved read surface. Parent enforces a deadline, kills/reaps overdue readers,
   caps output size and prevents overlapping refresh cycles. A broken source cannot
   stop healthy adapters or spawn unlimited workers.
3. Readers return normalized, allowlisted metadata. Parent validates it, resolves
   context semantics through the shared contract/limit registry, and holds one
   bounded snapshot per provider in memory. No raw records/errors reach the UI.
4. `GET /api/snapshot` returns that cache; browser requests do not trigger provider
   polls. Static UI renders with `textContent`, never provider HTML. Empty registry
   is a real not-connected state, not a demo fallback.

Poll interval: 5 seconds, configurable minimum 2 seconds. Reader deadline: 2 seconds.
Maximum configured providers: 16; at most 4 readers run at once. Maximum 50 selected
sessions per provider, 4 MiB worker response, 64 MiB source file scan and 1 MiB JSONL
line. Exceeding a budget produces explicit truncated/unavailable evidence, never a
silent complete result. Readers bound database operations and file scans; parent
deadline is the final containment boundary. Removal drops cached sessions on the
next registry application; contract tests must prove add/remove without UI edits.

### Shared model and limits (ACC-08 owns implementation)

Provider snapshot: provider ID/display name, source status, observation time,
static redacted error code/reason, source version, sessions and truncation flag.
Session: provider+session ID, optional parent ID, exact model, source, source event
time, activity enum (`unknown`, `idle`, `busy`, `ended`) with provenance, freshness,
context and optional numeric pressure/history fields. Task labels are unavailable
unless a separately approved metadata surface provides them; never use titles or
first prompts. Audit events contain type/result/correlation/time, not prompt text.

Do not equate source connectivity, session lifecycle, and metric freshness.
A successful read does not refresh an old measurement's timestamp. Measurement
age >30 seconds is stale, missing/invalid timestamp is unknown, >5 minutes is
expired. Preserve original event time. A source error may retain a previous
snapshot for at most 5 minutes with explicit error/stale status; expired samples
lose values. Lifecycle may remain unknown even with a fresh metadata measurement.
Never prove activity merely from an open database row or unfinished start event.

Context fields separately carry numerator, limit, semantic (`occupancy`,
`last_request_input`, `unavailable`), model+route identity, source and event time.
The limit registry keys by provider ID + exact model + normalized route, and also
accepts a validated same-measurement provider-reported limit. Route normalization
only strips trailing slashes/whitespace; do not merge different endpoints, schemes
or unknown routes. Unknown route cannot match a static model-name catalogue.
No default limits or fetching a public model catalogue during polling.

A percentage requires nonnegative integer **occupancy** numerator, positive known
compatible denominator, identical model/route identity, and fresh timestamp.
Booleans, NaN, infinity, impossible values (>limit), stale samples and mismatches
suppress percentages with explicit reasons. `last_request_input` can be shown as
historical API input but never as a current fullness gauge. Lifetime token totals
are excluded from this calculation. Keep provenance on both values.

### First integration and provider boundaries

Implement ACC-09 first: approved gateway `identify`/`status` and read-only session
metadata. Gateway health is separate from individual session activity. Pressure
fields use SQL aggregates over `active`, `compacted` and summary flags; no message
content. Counts are historical folding indicators, not overflow counts or fullness.
Then verify a neutral real-session UI slice before adding the other adapters.
ACC-12's final styling stays pending Jimmy's approval; its neutral list may proceed.

ACC-10 uses registrations and selected parent/child transcript metadata. PID reads
must account for observer namespaces; no accessible process is not automatically
proof of offline. ACC-PA-codex uses read-only indexed metadata and selected rollout
fields; a stored task is not necessarily active. Neither adapter invokes a provider
CLI, starts an app-server, installs hooks, resumes, subscribes or sends anything.

## Retention and local security boundary

Default to memory only, with the bounds above; do not persist telemetry, provider
messages, prompts or raw errors. Source files remain in their owning providers.
A restart clears cache, draft/send confirmations and audit events. No conversation
import. Read roots and selected IDs are trusted server config, never HTTP parameters.
Resolve paths inside those roots, reject symlink escape, avoid raw path disclosure,
open SQLite `mode=ro` with query-only mode, never immutable/WAL checkpoint/repair.
Treat records as data; never execute embedded commands or dynamic module names.

Serve only an exact static-file allowlist and JSON endpoints. Require exact
loopback Host and same-origin browser requests; reject foreign Origin and fetch
metadata. No CORS, directory listing, arbitrary filesystem path, or traceback
responses. Use restrictive CSP, no-store, nosniff and frame denial. Suppress HTTP
request logging; diagnostics use fixed codes. Protect all future writes with a
per-process random CSRF token plus strict Origin/Host checks. Tokens stay in page
memory, never localStorage/cookies/URL query strings.

### ACC-16 vault decision

Target the installed Linux Secret Service through `/usr/bin/secret-tool`, called
only from backend with secrets on stdin (not arguments). Store only the application's
own namespace and provider ID, never inspect/import existing provider credentials.
No fallback to plaintext files, environment variables or browser storage. Missing,
locked, cancelled or timed-out vault operations fail closed with redacted errors.
Bound input size and subprocess duration; never echo submitted secrets. Presence
and last local validation time are separate from remote key validity. Do not label
syntactic validation or successful storage as provider authentication. No remote
validation request without an explicit configured supported validator.

Before enabling key entry, ACC-16 must verify this threat model with tests and a
disposable non-secret value in its own namespace, or document why live vault
verification is blocked. Same-user malicious processes are outside this local app's
isolation guarantee; they already have the user's OS-vault access. Different-origin
web pages and accidentally logged secrets are in scope. UI shows presence only.

### ACC-17 message boundary

Existing read-only adapters grant **no send capability**. A distinct capability
must name a verified transport and target semantics before a real send is enabled.
No background dispatch, external shared channel or provider attachment by inference.
All sends require a short-lived, one-use server-bound confirmation covering exact
provider/session, prompt, workspace, expected effect and side effects; editing
invalidates it. User can cancel. Replays or target changes fail closed. Audit only
actor/target/time/correlation/lifecycle, with results awaiting operator review.

Keep drafts and any intentionally submitted chat in bounded memory only; provide
clear/delete and discard on restart. Provider-published messages are inert text;
private hidden reasoning is never imported. If no approved send surface can be
verified without changing provider operation, ACC-17 remains blocked with that
exact prerequisite; a fake dispatcher cannot satisfy it. The requested entire
backend phase therefore includes this gate, not permission to silently omit it.

## Options considered and trade-offs

| Option | Complexity | Cost | Fit |
| --- | --- | --- | --- |
| Python standard library (chosen) | Small custom HTTP/security surface; direct SQLite/socket support | No dependency installs or network at runtime | Installed; bounded single-user local service |
| Python web framework | Better routing/schema tooling, additional runtime dependencies | Installation/version maintenance | Revisit if authenticated multi-user API is approved |
| Node service | Strong UI ecosystem, extra care for local SQLite/runtime compatibility | No benefit for current static neutral UI | Installed, but Python matches all three existing storage surfaces |

Consequences: straightforward metadata readers and offline reproducible setup;
manual HTTP validation requires focused tests. No typechecker package is installed;
syntax compilation, strict runtime contract validation and behavioral tests are
required. Formatting checks cover project whitespace/JSON and compile Python;
these must not be mislabelled static typechecking. A framework and static typechecker
can be introduced later with a demonstrated need.

## Implementation actions and evidence

ACC-07 builds shell/setup/lock/CI; ACC-08 proves model+registry and failure isolation;
ACC-09 verifies first reader; neutral ACC-12/13 provides the required slice;
ACC-10 and ACC-PA-codex follow; ACC-16 verifies the local vault; ACC-17 requires a
verified send surface. Each implementation receives a separate subagent review,
Library handoff and Git integration. Phase 3 remains the broader audit.

Checks for this ADR: installed Python/Node and secret-tool existence inspected;
all discovery dependencies accepted by `/root/discovery_review`; task definitions
and completion plan copied byte-for-byte from existing `d67da97`; `git diff --check`.
No listener, credential operation, remote message, or application capability is
claimed by this architecture document.
