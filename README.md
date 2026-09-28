# AI Command Center

A local-first dashboard for Jimmy to oversee agent sessions, with trustworthy context-window visibility and a readable 16-bit-inspired interface. Hermes, Claude Code and Codex are the first providers; providers are pluggable by design.

**Current deliverable: the execution plan. No application has been built yet.**

## Start here, agents

1. Read [AGENTS.md](AGENTS.md).
2. Open the canonical work queue: `/home/jimmy/Library of Alexandria/AI Command Center/Plan of Attack.md`.
3. Pick one eligible task, claim it, and execute its [task specification](docs/TASKS.md).
4. Deliver verifiable files and a handoff. Check off only what was actually verified.

Library overview: `/home/jimmy/Library of Alexandria/AI Command Center.md`.
GitHub holds code, technical specifications and test evidence. The Library holds task status, ownership, decisions and handoffs. Do not create a second issue tracker or copy task status into this README.

If you cannot access the Library, use an explicit task assignment from Jimmy/operator, work in an isolated branch, and return the handoff for synchronization. Do not guess ownership or claim the whole project is complete.

## First milestone

One real provider session displayed locally with source, timestamp and honest context availability. A beautiful mockup alone does not meet this milestone.

The committed visual reference lives at `docs/design/reference/16bit-ops-room-reference.webp`. It is inspiration, not a specification: its approval controls, token burn-rate gauge, reasoning-text panel and confidence metric are all out of scope or unavailable. See ACC-05.

See [task specifications](docs/TASKS.md), [completion rules](docs/WORKFLOW.md), and [handoff template](docs/HANDOFF-TEMPLATE.md).

## Scope

- Independent read-only adapters behind a provider registry. Hermes, Claude Code and Codex are active; Buzz is deferred. Adding or removing a provider is a registry entry plus one adapter module, never a plan amendment.
- Context values only when measured against a known compatible model limit.
- Explicit unavailable, stale, offline and error states.
- Localhost only. Messaging, Telegram commands, remote access and deployment are later decisions.

There are no installation or application test commands yet. ACC-07 must add and verify them when the application exists.

## Reusable assignment

> Work on AI Command Center. Read the repository AGENTS.md and the Library Plan of Attack. Complete one eligible unclaimed task, using the claim procedure and an isolated branch. Deliver its named artifacts, run its acceptance checks, and append a handoff in its Library task note. Mark review when delivered; never mark unverified work done. Do not deploy or message other agents.

For the first connector investigations, assign ACC-02 (Hermes), ACC-03 (Claude Code) and ACC-PV-codex (Codex) to different agents explicitly. Those tasks write separate files and can proceed independently.
