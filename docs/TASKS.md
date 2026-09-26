# Task specifications

Task status and checkboxes live in the Library. These specifications define the work, not its current completion state.

Initially eligible: ACC-01–ACC-05. ACC-00 is plan installation.

## ACC-01 — Recover existing work and reconcile status

Dependencies: None.

Deliverable: `docs/discovery/prior-work.md`.

Inspect the canonical repository, Library, and accessible project-specific handoffs. Recover any Hermes/Pollen/Honey/Fizz results without sending messages or restarting agents.

Acceptance:
- List each source checked and date; distinguish delivered, unpublished, and not accessible.
- Link or preserve each relevant result with provenance; do not treat chat claims as tested code.
- List contradictions and the current owner of unresolved work. A documented no-results finding is valid.


## ACC-02 — Verify Hermes telemetry

Dependencies: None.

Deliverable: `docs/discovery/hermes.md`.

Inspect the installed Hermes version and documented/local read interfaces using one non-sensitive session.

Acceptance:
- Record installed version, source path/API, and reproducible read-only checks.
- Verify session identity, activity, model, context tokens and context limit separately; distinguish context occupancy from cumulative usage.
- Include sanitized sample data and field availability/freshness. If unavailable, document the attempted checks and exact limitation.
- Identify the smallest safe adapter surface; do not read or export secrets or full conversation content.


## ACC-03 — Verify Claude Code telemetry

Dependencies: None.

Deliverable: `docs/discovery/claude-code.md`.

Check what the installed Claude Code exposes for parent and background-agent sessions.

Acceptance:
- Record version and read-only evidence for session discovery, status and model.
- Verify whether each context measurement belongs to the parent or child session, and whether its denominator is known.
- Include sanitized samples and unavailable/stale behavior; do not infer occupancy from billing token totals.
- Document permissions and a reproducible check without copying conversation contents or credentials.


## ACC-04 — Verify Buzz telemetry

Dependencies: None.

Deliverable: `docs/discovery/buzz.md`.

Inspect accessible Buzz documentation and local integration surfaces. Read project-specific coordination only if already accessible; do not send messages or join channels.

Acceptance:
- Identify which source actually owns agent/session telemetry; a chat message is not authoritative runtime status.
- Record version/API/source and sanitized examples for available fields.
- Verify context metrics or explicitly document unsupported fields and failed checks.
- Document read permissions, offline behavior and rate limits where known; never expose private keys.


## ACC-05 — Define the first dashboard screen

Dependencies: None.

Deliverable: `docs/design/first-screen.md and an original mockup under docs/design/`.

Use the recorded 16-bit isometric reference as inspiration for a readable operational screen. Inspect the image before claiming visual comparison.

Acceptance:
- Show agent/session identity, activity, context used/limit, measurement source, updated time, stale/unavailable states and errors.
- Use explicitly labeled sample data in mockups; never present it as live telemetry.
- Include keyboard navigation, readable text, reduced motion, narrow-window layout and a plain list view.
- Present one recommended design and list consequential choices for Jimmy. Mark visual approval pending until received; backend tasks may proceed.


## ACC-06 — Choose the MVP architecture

Dependencies: ACC-01, ACC-02, ACC-03, ACC-04.

Deliverable: `docs/architecture.md`.

Synthesize discovery into one bounded local-only implementation plan. Choose tools from demonstrated needs; do not research indefinitely.

Acceptance:
- Name the chosen stack, localhost startup approach, data flow and smallest first integration, with evidence-based reasons.
- Define adapter boundaries, timeout/error isolation, credential handling and storage/retention; default to memory and minimal metadata.
- Define freshness thresholds and prohibit deriving percent used without compatible numerator/denominator.
- List unsupported metrics honestly and decide what the first release can prove. Remote access, messaging and deployment stay out of scope.


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

Deliverable: `Shared adapter interface, normalized models and contract tests`.

Implement one normalized session model and adapter interface for the three providers.

Acceptance:
- Model source/provider/session/model identity, activity status, observed time, freshness, context used/limit and explicit unavailable reason.
- Keep lifecycle status separate from context freshness; unknown is never silently zero.
- Test missing limits, zero limits, mismatched measurements, stale data, malformed input and provider errors.
- Adapters are independently replaceable and cannot execute instructions from telemetry.


## ACC-09 — Implement Hermes read-only adapter

Dependencies: ACC-02, ACC-08.

Deliverable: `Hermes adapter and focused tests`.

Implement only the supported read surface established by ACC-02.

Acceptance:
- Acquire real sanitized session metadata and supported context values from the configured local source.
- Test offline/missing source, timeout, malformed data and stale measurements.
- Unsupported metrics show unavailable with a reason; do not fabricate a substitute percentage.
- Record a reproducible live read and test evidence; do not change or dispatch Hermes sessions.


## ACC-10 — Implement Claude Code read-only adapter

Dependencies: ACC-03, ACC-08.

Deliverable: `Claude Code adapter and focused tests`.

Implement the supported surface established by ACC-03; preserve parent/child session identity.

Acceptance:
- Show real session metadata where available; label unsupported fields instead of guessing.
- Test parent/child mapping, missing credentials/source, malformed input and stale data.
- Verify one real read when access exists, or mark integration verification blocked with exact required access.
- No prompt content, secrets or unrelated session history is exposed.


## ACC-11 — Implement Buzz read-only adapter

Dependencies: ACC-04, ACC-08.

Deliverable: `Buzz adapter and focused tests`.

Implement the verified Buzz read interface established by ACC-04.

Acceptance:
- Keep chat presence separate from verified agent execution status.
- Test unavailable telemetry, offline/permission failure and malformed records without breaking other adapters.
- Verify one real read when access exists, or mark integration verification blocked with exact required access.
- No joining, sending, agent dispatch, credential changes or invented context metrics.


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

Also requires ONE of ACC-09/10/11 fully verified. Connect that adapter to the real UI before expanding integration work.

Acceptance:
- Show at least one real session end to end with provenance and updated time.
- Show real context values if supported; otherwise clearly demonstrate unavailable and state that context visibility is not yet proven.
- Disconnect the source and show a contained error/stale state; reconnect without restarting unrelated integrations.
- Record source version, revision, steps and screenshots; never claim a running mockup is an integrated dashboard.


## ACC-14 — Combine providers and verify isolation

Dependencies: ACC-09, ACC-10, ACC-11, ACC-13.

Deliverable: `Provider composition and docs/verification/multi-provider.md`.

Combine independently verified adapters. If one cannot be verified, leave this task blocked; propose a smaller release explicitly rather than marking it complete.

Acceptance:
- Show each provider independently with real verified data or explicit field-level unavailability.
- A failing provider does not stop or erase healthy providers.
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
