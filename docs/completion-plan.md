# AI Command Center completion plan

This plan groups the existing and newly requested work into three delivery phases. Task state remains authoritative in the linked ACC notes in the Library; this document is a sequence, not a second status tracker.

## Phase 1 — Backend

### Backend

#### Major tasks

- [ ] Confirm provider capabilities and source-of-truth fields for sessions, live task, context usage/limit, timestamps, errors, and send support. Reuse ACC-01–04 and ACC-PV provider instances; do not infer capabilities.
- [ ] Choose the local architecture and data-retention model (ACC-06): loopback-only process, provider registry, adapter isolation, timeouts, normalized models, credential boundary, and explicit unavailable/stale/error states.
- [ ] Build the runnable local shell and shared contracts (ACC-07/08): session identity, parent/child relationships, task/run lifecycle, context numerator/denominator/source, freshness, and audit events.
- [ ] Implement and verify provider adapters one at a time (ACC-09/10 and ACC-PA instances); deliver one real vertical slice before expanding.
- [ ] Implement the local OS credential-vault adapter and provider connection lifecycle (ACC-16) before accepting API-key input.
- [ ] Implement message transport only after a send-capable surface is verified; model brain-to-specialist conversation without assuming a new external channel (ACC-17).

#### Minor tasks

- [ ] Keep providers pluggable: provider identity lives in its adapter/registry, not shell-specific branches.
- [ ] Normalize `connected`, `offline`, `stale`, `unsupported`, `permission denied`, and `error` separately from context availability.
- [ ] Persist only minimum necessary session/chat metadata; define retention and deletion controls before saving transcripts.
- [ ] Return message-send results to operator review. Never auto-accept a worker result or treat a chat message as proof of a running task.
- [ ] Keep provider/API secrets in the OS credential vault; never pass them to browser storage or UI telemetry.

## Phase 2 — Front end

### Front end

#### Major tasks

- [ ] Turn the approved pixel-art monitor design into the local dashboard shell; keep a plain list mode equivalent to the isometric room.
- [ ] Build the agent/session overview: provider, role, session identity, current task/run state, freshness, source, and clear unavailable/error states.
- [ ] Build the shared brain/specialist conversation view with role attribution, task updates, concise public-facing summaries, safe action/tool outcomes, and local transcript boundaries.
- [ ] Build measured context panels: actual used/limit only with a compatible denominator; show occupancy unavailable where discovery says it cannot be read. Never substitute cumulative tokens or burn rate.
- [ ] Build provider configuration: add/replace/remove credentials through backend vault operations; show masked presence and validation status, never the secret.
- [ ] Add a deliberate send flow that previews exact target, session/channel, message, workspace, expected effects and side effects before confirmation.

#### Minor tasks

- [ ] Maintain 16-bit colors, crisp pixel sprites and distinct agent roles without sacrificing contrast or usable text size.
- [ ] Support keyboard navigation, visible focus, screen-reader labels, reduced motion, narrow screens, long provider/session names, and dense histories.
- [ ] Render all agent/provider content as inert text; do not inject transcript HTML.
- [ ] Mark demo fixtures clearly; production mode must never silently fall back to demo telemetry.
- [ ] Include loading, empty, disconnected, stale, failed, permission-denied, and successful states for every view.

## Phase 3 — Security and testing

### Security

#### Major tasks

- [ ] Complete a local threat model before live chat or credential entry: untrusted provider text, local browser origin, filesystem/database access, secret leakage, transcript retention, and unintended agent actions.
- [ ] Enforce loopback-only binding and validate origin/CSRF protections for any local write endpoint.
- [ ] Verify OS credential-store behavior for save, replace, validation, unlock/locked, revoke/delete and error paths.
- [ ] Require explicit per-send confirmation; log actor, target, timestamp, correlation ID and lifecycle without logging API keys or private prompt data unnecessarily.
- [ ] Separate safe action summaries and provider-published explanations from private hidden chain-of-thought; do not display or persist private reasoning transcripts.

#### Minor tasks

- [ ] Redact secrets from logs, exception messages, diagnostics, exported files, screenshots and browser responses.
- [ ] Define retention defaults, purge behavior, workspace/path restrictions, and transcript export rules.
- [ ] Verify provider content cannot trigger local commands, change configuration, or bypass confirmation.
- [ ] Verify cancel/reject/failed-send does not leave an ambiguous success state.

### Testing

#### Major tasks

- [ ] Unit and contract tests for model validation, context-limit matching, unavailable/stale/error states, provider registry changes, task lifecycle and audit events.
- [ ] Adapter integration tests against verified local sources; cover missing/locked credentials, permission errors, timeouts, malformed responses, stale data and disconnect/reconnect.
- [ ] End-to-end tests for provider setup, brain-bot chat, shared specialist updates, send confirmation/cancel, and operator review of results.
- [ ] UI tests for keyboard-only operation, screen-reader labels, reduced motion, responsive breakpoints, long names, many sessions, and plain-list parity.
- [ ] Security tests proving no secrets leak to browser storage, HTTP responses, logs, crash paths, or repository artifacts; prove untrusted transcript text is inert.

#### Minor tasks

- [ ] Verify context occupancy against provider-reported values and the exact model/base URL limit; reject mismatched or unknown denominators.
- [ ] Verify timestamps and sources are shown for every live metric; do not show simulated values as live.
- [ ] Capture desktop and narrow-window screenshots for final visual review; record known limitations and reproducible commands.
- [ ] Run the documented clean install, format/typecheck, test, build and loopback smoke checks from a fresh worktree.

### Final review and last-minute fixes

- [ ] Review all three providers independently; one failing connector must not hide healthy providers.
- [ ] Confirm open/complete task status is reflected in the Library, not duplicated here.
- [ ] Review the complete diff for secret leakage, unrequested remote/channel behavior, misleading telemetry, and unfinished placeholders.
- [ ] Have Jimmy approve the visual direction and credential/chat flows before enabling live writes.
- [ ] Fix only release-blocking issues; rerun affected tests and the full release suite.
- [ ] Record revision, evidence, remaining risks, startup/shutdown steps, and explicit non-goals in the release handoff.
- [ ] Do not publish, deploy, enable remote access, or send a real message until separately approved.
