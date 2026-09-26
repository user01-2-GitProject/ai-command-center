# Execution and completion rules

## Sources of truth

- Library: current ownership, task status, decisions and append-only handoffs.
- GitHub: stable task specifications, implementation, technical evidence and code history.
- Slack/Buzz/Telegram: coordination only when explicitly authorized. Do not introduce another tracker.
- Task specifications here are intentionally unchecked. Check off acceptance items in the corresponding Library task note; this avoids two competing status boards.

## States

`todo` → `in_progress` → `review` → `done`; use `blocked` for a concrete unmet prerequisite.

A blocked task must name the exact missing input/access, attempted checks and next unblock action. Never mark it done because time ran out. An unavailable telemetry field can be a valid discovery result; an untested adapter is not a verified integration.

## Claim safely

On Jimmy's machine, use the shared canonical checkout as the claim location, even when coding in another worktree:

```sh
mkdir -p /home/jimmy/Projects/ai-command-center/.task-claims
mkdir /home/jimmy/Projects/ai-command-center/.task-claims/ACC-02
```

Replace ACC-02 with your task ID. The second mkdir is an atomic claim: if it already exists, do not overwrite it or take the task. Inspect its owner and choose another eligible task. In the claimed directory, write `owner.txt` with agent/session ID, UTC timestamp and workspace path; update the matching Library task note immediately. A crash between these steps leaves a reservation; operator must verify the owner is inactive before releasing it. Age alone is not permission to steal it.

Also check the Library owner before claiming. The operator must reserve explicitly assigned remote tasks using the same mechanism. Agents without Library/shared filesystem access must use an explicit assignment and submit their handoff for operator synchronization; they cannot self-claim safely.

Use one branch/worktree per task, named `task/ACC-NN-short-description`. Read git status before edits. Different agents own different task notes and output paths. Task ACC-08 defines the common interface before adapter/UI work starts.

## Bounded research

Discovery tasks deliver a named evidence file, not a promise to investigate. Start from installed/local sources and official documentation. After a focused attempt, record unavailable/access limitations instead of expanding indefinitely. Work that needs missing access moves to blocked; independent tasks continue. Existing unpublished work may be reused after verification and attribution.

## Handoff and acceptance

1. Run task-specific checks. Include commands/steps, result, date and source/revision. Do not run unnecessary broad checks for documentation-only changes.
2. Put reusable technical evidence under the task's specified repo path; keep credentials and raw private session content out.
3. Update your Library task acceptance checkboxes and append a handoff. Set `review`, with an evidence link/path. A commit/PR alone is not proof the behavior works.
4. Operator or separately assigned reviewer verifies deliverables against acceptance criteria and records accepted/rejected with evidence. Implementation must be integrated before setting `done`; link the canonical commit. Documentation needs explicit accepted evidence.
5. Clear only your own reservation after handoff, using its exact directory path. Preserve the owner/history in the Library. `review` is not available for a second implementation claim.
6. If a review fails, reopen with remaining checks intact and append the failure. Do not erase earlier attempts.

## First release boundary

First prove ACC-13: one real session end to end. Continue toward ACC-14/15 for all three providers. If a provider cannot be supported, explicitly propose a smaller release to Jimmy; do not quietly check off unsupported integration work. Final retro visual styling requires Jimmy's design approval; neutral accessible UI and backend work can proceed beforehand.

Later work, not part of this queue: sending prompts, approvals that trigger agents, Telegram commands, token cost forecasting, remote access and production hosting.
