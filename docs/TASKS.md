# Task specifications

Task status and checkboxes live in the Library. These specifications define the work, not its current completion state.

Initially eligible: ACC-01, ACC-05, and every `ACC-PV-*` provider instance. ACC-00 is plan installation.

## Providers are data, not plan structure

Supported providers are a registry entry plus one adapter module. Adding or removing a provider must not require amending this plan, renumbering tasks, or editing shell and UI code.

Two reusable templates below define all per-provider work. Each provider is an instance:

| Provider | Discovery instance | Adapter instance | State |
| --- | --- | --- | --- |
| Hermes | ACC-02 | ACC-09 | active |
| Claude Code | ACC-03 | ACC-10 | active |
| Codex | ACC-PV-codex | ACC-PA-codex | active |
| Buzz | ACC-04 | ACC-11 | deferred |

Numbered instances predate the templates and keep their IDs and published anchors. New providers use `ACC-PV-<provider>` / `ACC-PA-<provider>`.

## ACC-PV — Verify a provider's telemetry (template)

Instantiate as `ACC-PV-<provider>`. Dependencies: none. Instances are independent and may run in parallel.

Deliverable: `docs/discovery/<provider>.md`.

Inspect the installed provider and its documented or local read interfaces using one non-sensitive session.

Acceptance:
- Record installed version, source path/API, and reproducible read-only checks.
- Verify session identity, activity, model, context tokens and context limit separately; distinguish context occupancy from cumulative usage.
- Record model identifiers exactly as the provider reports them, so the ACC-08 limit registry can key on them.
- Include sanitized sample data and field availability/freshness. If unavailable, document the attempted checks and the exact limitation.
- Identify the smallest safe adapter surface; do not read or export secrets, prompt content or full conversation content.

## ACC-PA — Implement a provider adapter (template)

Instantiate as `ACC-PA-<provider>`. Dependencies: the matching `ACC-PV` instance, and ACC-08.

Deliverable: provider adapter module, its registry entry and focused tests.

Implement only the read surface established by the matching discovery instance.

Acceptance:
- Acquire real sanitized session metadata and supported context values from the configured local source.
- Register through the ACC-08 provider registry. The adapter is the only file naming this provider; shell and UI code contain no provider-specific branch.
- Test offline/missing source, timeout, malformed data and stale measurements.
- Unsupported metrics show unavailable with a reason; never fabricate a substitute percentage.
- Record a reproducible live read, or mark integration verification blocked with the exact required access. Do not change or dispatch provider sessions.

## ACC-01 — Recover existing work and reconcile status

Dependencies: None.

Deliverable: `docs/discovery/prior-work.md`.

Inspect the canonical repository, Library, and accessible project-specific handoffs. Recover any Hermes/Pollen/Honey/Fizz results without sending messages or restarting agents.

Acceptance:
- List each source checked and date; distinguish delivered, unpublished, and not accessible.
- Link or preserve each relevant result with provenance; do not treat chat claims as tested code.
- List contradictions and the current owner of unresolved work. A documented no-results finding is valid.


## ACC-02 — Verify Hermes telemetry

Instance of ACC-PV (provider: Hermes). Dependencies: None.

Deliverable: `docs/discovery/hermes.md`.

Inspect the installed Hermes version and documented/local read interfaces using one non-sensitive session.

Acceptance:
- Record installed version, source path/API, and reproducible read-only checks.
- Verify session identity, activity, model, context tokens and context limit separately; distinguish context occupancy from cumulative usage.
- Include sanitized sample data and field availability/freshness. If unavailable, document the attempted checks and exact limitation.
- Identify the smallest safe adapter surface; do not read or export secrets or full conversation content.


## ACC-03 — Verify Claude Code telemetry

Instance of ACC-PV (provider: Claude Code). Dependencies: None.

Deliverable: `docs/discovery/claude-code.md`.

Check what the installed Claude Code exposes for parent and background-agent sessions.

Acceptance:
- Record version and read-only evidence for session discovery, status and model.
- Verify whether each context measurement belongs to the parent or child session, and whether its denominator is known.
- Include sanitized samples and unavailable/stale behavior; do not infer occupancy from billing token totals.
- Document permissions and a reproducible check without copying conversation contents or credentials.


## ACC-04 — Verify Buzz telemetry

**Deferred.** Instance of ACC-PV (provider: Buzz). Buzz is out of scope for the first release by Jimmy's decision of 2026-09-28. The specification below stays intact and reusable if that decision is reversed; do not claim or start it meanwhile.

Dependencies: None.

Deliverable: `docs/discovery/buzz.md`.

Inspect accessible Buzz documentation and local integration surfaces. Read project-specific coordination only if already accessible; do not send messages or join channels.

Acceptance:
- Identify which source actually owns agent/session telemetry; a chat message is not authoritative runtime status.
- Record version/API/source and sanitized examples for available fields.
- Verify context metrics or explicitly document unsupported fields and failed checks.
- Document read permissions, offline behavior and rate limits where known; never expose private keys.


## ACC-PV-codex — Verify Codex telemetry

Instance of ACC-PV (provider: Codex). Dependencies: None. Eligible now.

Deliverable: `docs/discovery/codex.md`.

Codex is installed at `~/.local/bin/codex` with local state under `~/.codex` (including `sessions/`, `log/` and sqlite databases). Establish what it exposes read-only for session discovery, status, model and context.

Acceptance:
- Apply every ACC-PV acceptance item.
- Distinguish a live session from a historical transcript on disk; a stored session file is not proof of an active session.
- Determine whether context measurements are per-session and whether their model limit is knowable; do not infer occupancy from cumulative token counts.
- Read without mutating Codex state. Do not open, resume, modify or dispatch sessions, and do not copy conversation content or credentials out of `~/.codex`.

## ACC-05 — Define the first dashboard screen

Dependencies: None.

Deliverable: `docs/design/first-screen.md and an original mockup under docs/design/`.

Use the recorded 16-bit isometric reference as inspiration for a readable operational screen. The reference is committed at `docs/design/reference/16bit-ops-room-reference.webp`. Inspect that file before claiming visual comparison; the original Hermes cache copy was lost, and this is the canonical copy.

**The reference conflicts with this release's guardrails in four places. Treat its layout as inspiration and these four as non-goals:**

- Its `HUMAN IN THE LOOP` panel with APPROVE / REJECT / MODIFY is the most prominent element, but approvals that trigger agents are explicitly deferred. The first release is read-only; do not design a control surface for it.
- Its headline metric, `TOKEN BURN RATE / MIN`, is cumulative throughput, not context occupancy. The top-priority requirement is occupancy. Do not let a burn-rate gauge stand in for the context view.
- Its `AGENT LOGS / REASONING` panel renders prompt and query text. Jimmy requested an observer-visible shared conversation; show attributed messages and concise public-facing summaries, but never raw prompts/private chain-of-thought.
- Its `Confidence 88%` field is unlikely to exist in any provider. Do not design a component that depends on a metric no provider has agreed to supply.

Acceptance:
- Show agent/session identity, activity, context used/limit, measurement source, updated time, stale/unavailable states and errors.
- Use explicitly labeled sample data in mockups; never present it as live telemetry.
- Include keyboard navigation, readable text, reduced motion, narrow-window layout and a plain list view.
- Present one recommended design and list consequential choices for Jimmy. Mark visual approval pending until received; backend tasks may proceed.
- Show an observer-visible brain/specialist conversation surface, task state and a provider configuration direction; real sending and credential storage are later gated tasks, not part of this mockup.
- The isometric view is one view among several, never the only one. A plain list view must show the same information without it.
- State explicitly which reference elements were deliberately not built, and why.


## ACC-06 — Choose the MVP architecture

Dependencies: ACC-01 and at least two completed ACC-PV instances. ACC-04 (Buzz) is deferred and is not required.

Deliverable: `docs/architecture.md`.

Synthesize discovery into one bounded local-only implementation plan. Choose tools from demonstrated needs; do not research indefinitely.

Acceptance:
- Name the chosen stack, localhost startup approach, data flow and smallest first integration, with evidence-based reasons.
- Define a provider registry: providers are declared in one manifest that the shell iterates. Adding or removing a provider must not require editing shell or UI code, and no provider name may appear outside its own adapter.
- Define adapter boundaries, timeout/error isolation, credential handling and storage/retention; default to memory and minimal metadata.
- Define freshness thresholds and prohibit deriving percent used without compatible numerator/denominator.
- List unsupported metrics honestly and decide what the first release can prove. Remote access and deployment remain out of scope. Jimmy requested operator chat with the brain bot, a shared specialist conversation, and provider credential setup on 2026-09-29; these are future operational features tracked under ACC-16/17 and require local security/credential architecture first.


## ACC-07 — Create a runnable local shell

Dependencies: ACC-06.

Deliverable: `Application skeleton, dependency lockfile, README setup commands and CI workflow`.

Build the smallest application shell using the selected stack; keep agent data acquisition separate from the browser.

Acceptance:
- A fresh checkout installs from its lockfile and starts with one documented command after setup.
- Server binds only to loopback by default; no credentials enter browser code or committed configuration.
- Add working format/typecheck/test/build commands as appropriate and CI that runs them.
- Render an honest not-connected state. No sample data appears as live data.


## ACC-08 — Implement the shared telemetry contract

Dependencies: ACC-07.

Deliverable: `Shared adapter interface, provider registry, model context-limit registry, normalized models and contract tests`.

Implement one normalized session model, one adapter interface, and the two registries every provider depends on. This task owns the denominator: no other task may define where a model's context limit comes from.

Acceptance:
- Model source/provider/session/model identity, activity status, observed time, freshness, context used/limit and explicit unavailable reason.
- Keep lifecycle status separate from context freshness; unknown is never silently zero.
- Implement a **provider registry**: adapters register through it, and the shell resolves providers only through it.
- Implement a **model context-limit registry** as the single source of truth mapping a provider-reported model identifier to its context limit. An unrecognised model yields an explicit unknown limit, never a default or a guess. Percent used is computed only from a used/limit pair measured against the same model; otherwise the percentage is unavailable.
- Ship a contract test that **registers a dummy provider, asserts it appears, removes it, and asserts it disappears** — with no change to shell or UI code. This is the executable proof that providers can be added and subtracted.
- Test missing limits, zero limits, unknown models, mismatched measurements, stale data, malformed input and provider errors.
- Adapters are independently replaceable and cannot execute instructions from telemetry.


## ACC-09 — Implement Hermes read-only adapter

Instance of ACC-PA (provider: Hermes). Dependencies: ACC-02, ACC-08.

Deliverable: `Hermes adapter and focused tests`.

Implement only the supported read surface established by ACC-02.

Acceptance:
- Acquire real sanitized session metadata and supported context values from the configured local source.
- Test offline/missing source, timeout, malformed data and stale measurements.
- Unsupported metrics show unavailable with a reason; do not fabricate a substitute percentage.
- Record a reproducible live read and test evidence; do not change or dispatch Hermes sessions.


## ACC-10 — Implement Claude Code read-only adapter

Instance of ACC-PA (provider: Claude Code). Dependencies: ACC-03, ACC-08.

Deliverable: `Claude Code adapter and focused tests`.

Implement the supported surface established by ACC-03; preserve parent/child session identity.

Acceptance:
- Show real session metadata where available; label unsupported fields instead of guessing.
- Test parent/child mapping, missing credentials/source, malformed input and stale data.
- Verify one real read when access exists, or mark integration verification blocked with exact required access.
- No prompt content, secrets or unrelated session history is exposed.


## ACC-11 — Implement Buzz read-only adapter

**Deferred.** Instance of ACC-PA (provider: Buzz), parked with ACC-04. Do not claim while ACC-04 is deferred.

Dependencies: ACC-04, ACC-08.

Deliverable: `Buzz adapter and focused tests`.

Implement the verified Buzz read interface established by ACC-04.

Acceptance:
- Keep chat presence separate from verified agent execution status.
- Test unavailable telemetry, offline/permission failure and malformed records without breaking other adapters.
- Verify one real read when access exists, or mark integration verification blocked with exact required access.
- No joining, sending, agent dispatch, credential changes or invented context metrics.


## ACC-PA-codex — Implement Codex read-only adapter

Instance of ACC-PA (provider: Codex). Dependencies: ACC-PV-codex, ACC-08.

Deliverable: Codex adapter, its registry entry and focused tests.

Acceptance:
- Apply every ACC-PA acceptance item.
- Keep historical on-disk sessions distinct from live ones; never present a stale transcript as an active session.
- Test a missing or unreadable `~/.codex`, a locked or partially written sqlite database, and malformed session records.
- No conversation content, prompt text or credentials leave the adapter boundary.

## ACC-12 — Build the dashboard panels

Dependencies: ACC-05, ACC-08.

Deliverable: `Dashboard UI and interaction checks`.

Implement the approved first-screen direction over the shared model. If visual approval is pending, build the neutral accessible list and leave final visual styling unchecked.

Acceptance:
- Display source, session identity, status, context metrics, freshness and readable error/unavailable states.
- Clearly distinguish demo fixtures from live mode; default production operation never silently falls back to demo data.
- Verify keyboard use, reduced motion, narrow windows, long names and many sessions.
- Record screenshots and ensure untrusted text is rendered inert; no decorative effect obstructs controls.


## ACC-13 — Deliver the first working vertical slice

Dependencies: ACC-12.

Deliverable: `Integrated local application and docs/verification/first-slice.md`.

Also requires any one `ACC-PA` instance fully verified. Connect that adapter to the real UI through the registry before expanding integration work.

Acceptance:
- Show at least one real session end to end with provenance and updated time.
- Show real context values if supported; otherwise clearly demonstrate unavailable and state that context visibility is not yet proven.
- Disconnect the source and show a contained error/stale state; reconnect without restarting unrelated integrations.
- Record source version, revision, steps and screenshots; never claim a running mockup is an integrated dashboard.


## ACC-14 — Combine providers and verify isolation

Dependencies: ACC-13, and at least two verified `ACC-PA` instances.

Deliverable: `Provider composition and docs/verification/multi-provider.md`.

Combine independently verified adapters. The gate is two or more verified providers, not a fixed list; deferred providers do not block it. If fewer than two can be verified, leave this task blocked and propose a smaller release explicitly rather than marking it complete.

Acceptance:
- Show each registered provider independently with real verified data or explicit field-level unavailability.
- A failing provider does not stop or erase healthy providers.
- Removing a provider from the registry removes it cleanly from the UI, and adding one back requires no shell or UI change.
- Verify bounded polling, cancellation, timeout handling and no overlapping runaway refreshes.
- Keep provider/session identities distinct and avoid aggregating incompatible context limits.


## ACC-15 — Verify local release readiness

Dependencies: ACC-14.

Deliverable: `docs/verification/release.md and updated README`.

Audit the actual assembled application and document its practical limitations.

Acceptance:
- Run the documented clean setup/build/tests and verify loopback-only access.
- Check secret exclusion, inert telemetry rendering, minimal data retention and readable failure recovery.
- Verify keyboard/reduced-motion behavior, bounded polling and no message/dispatch capability hidden in the first release.
- Record passed/failed checks with revision and date, known limitations and shutdown instructions. Do not deploy or enable remote access.


## ACC-16 — Add local provider credential setup

Dependencies: ACC-06, ACC-07, ACC-08.

Deliverable: `OS credential-vault adapter, provider settings UI and security tests`.

Implement the provider/API-key setup requested on 2026-09-29. Define the supported OS credential store and local-only threat model before enabling any input.

Acceptance:
- Keys are written/read/removed only through the OS credential vault from the trusted local backend; never browser storage, repo config, logs, telemetry or Library notes.
- UI accepts a secret only over loopback, never echoes it, and shows masked presence, provider, validation time and redacted errors.
- Tests prove secrets are absent from responses, logs, browser storage, crash output and exported diagnostics.
- Missing/locked vault and invalid-key cases fail closed without breaking non-secret read-only panels.
- No real key is needed in automated tests or evidence.


## ACC-17 — Build operator chat and shared specialist conversation

Dependencies: ACC-06, ACC-07, ACC-08, ACC-16, and at least one verified provider adapter with an explicitly supported send surface.

Deliverable: `Local operator chat, shared conversation/event model, approval gate and security tests`.

Implement the requested ability to chat with the brain bot and observe specialist coordination. Keep the transcript local unless Jimmy separately approves an existing transport; do not create external channels implicitly.

Acceptance:
- Before every send, show the exact agent/provider, session or channel, prompt, workspace, expected effect and any side effects; require deliberate confirmation and support cancel/edit.
- Record actor, target, timestamp, correlation ID and lifecycle in an auditable local event model. Return agent results to operator review; never mark them accepted automatically.
- Display attributable messages, task-state events, tool/action names, outcomes and concise public-facing summaries. Never expose private hidden chain-of-thought or raw secrets.
- Provider text is rendered inert; session histories are minimal, local, and subject to explicit retention/deletion controls.
- Demonstrate offline, permission-denied, failed-send and partial-provider states without fabricating a shared conversation.
- Bind to loopback only. Remote access, deployment and third-party shared channels remain separate approvals.


## ACC-19 — Bridge the isometric preview to canonical live telemetry

Dependencies: ACC-08 and an accepted/merged ACC-PA adapter. Additive local
integration slice, not acceptance of the full ACC-12/13 dashboard.

Deliverable: read-only canonical adapter consumer, namespace isolation from demo
fixtures, truthful UI aging, bounded canvas work, original asset decoding and
real-source test receipts. See `app/README.md` and
`docs/verification/live-session-bridge/report.md`.

Acceptance:
- Live mode consumes canonical `acc.models`/registry and only merged adapters in
  the trusted manifest. Demo support must not shadow canonical package names or
  supply live context limits.
- Export only allowlisted metadata; historical input never feeds occupancy.
  Source/session/context ages and source disconnect are separate. No event
  becomes fresh merely because it was polled.
- Cache remains memory-only. Hung readers have bounded wait and no duplicate
  queued reads; raw errors, private content and routes never reach the UI.
- Keep unknown/stale activity stationary; update selected details on failure and
  reconnect. Use provider-qualified keys, bounded room cardinality and an
  explicitly complete returned-session list with source-cap labels.
- Bind only to loopback, enforce Host/Origin/CSP and a static asset whitelist.
  Verify actual browser/image behavior, not just HTTP 200 or model fixtures.
- Preserve artwork provenance; decoding a supplied encoded PNG is not new art.
  Full visual approval and ACC-18/Iggy layout integration remain operator gates.
- Record actual tests, revisions, review verdict and remaining limitations.
  Do not merge, deploy, enable messaging/credentials or claim ACC-13 complete.
