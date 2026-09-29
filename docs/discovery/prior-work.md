# ACC-01 — Prior work recovered and reconciled

Audit date: 2026-09-29. Investigator: Codex, session
`01a0eee3-aec9-7c13-9d8c-ddbc91e91090`. Base: `53d8bcc`.
This is recovery evidence, not acceptance of another task or live telemetry verification.
Task status remains in the Library; this document is a dated snapshot.

## Sources checked

| Source | Result and provenance |
| --- | --- |
| Library `AI Command Center.md`, `AI Command Center/Plan of Attack.md`, and all task-note frontmatter | Accessible. ACC-00 done; ACC-02 and ACC-05 review; ACC-03 and ACC-PV-codex todo; Buzz deferred. Overview and plan prose lag the individual notes. |
| Canonical checkout `/home/jimmy/Projects (jimmy's)/ai-command-center` | Clean tracked/untracked status, local main at `cb43af6`. No application. Shared claim directory was empty before this task's atomic claim. |
| Git worktree/branch inventory and all-branch discovery history | Four existing worktrees located. Preserved user state; did not update other checkouts. Recovery artifacts below exist as Git objects. |
| GitHub `git ls-remote origin` for main and the two delivered task branches | Live verification: main `53d8bccd91658c5f828e2e826ab49e551c282196`; Hermes branch `a9ace6cc0724fc9f68cb9491630ecb859f71f50e`; no ACC-05 branch returned. First sandbox attempt failed DNS; retry with network permission succeeded. |
| ACC-02 task note and `docs/discovery/hermes.md` on its branch | Delivered, pushed, awaiting review. Corrections and pressure findings preserved across three commits. Provider reads were not rerun in ACC-01. |
| ACC-05 task note; design specification, HTML source, tree and completion plan at `d67da9737b62643c3b3c29f578830e3a7baefd17` | Delivered locally, unpublished under the named branch, awaiting visual/product review. Both screenshot files exist in its Git tree. Worktree `/home/jimmy/.local/share/ai-command-center/worktrees/ACC-05` is clean. Screenshots/browser interactions were not independently reverified here. |
| Project-specific handoff filenames in canonical checkout and ACC-05 worktree; named-worker references in Library project documents | Only generic handoff templates and the task-note histories were located. No separate Pollen/Honey/Fizz deliverable located in these sources. |
| Filename-only search of `~/.hermes/memories` and the Library for command-center/Pollen/Honey/Fizz Markdown artifacts | No additional matching project deliverable located. `~/.hermes/workspaces` and the old `/home/jimmy/Projects` path do not exist. No raw provider conversations, credentials, or unrelated memory bodies were read. |
| Earlier private agent conversations and external coordination channels | Not inspected. No claim that inaccessible work never occurred. Recover published project-specific handoffs through the operator if they exist; no messages or agent dispatch performed. |

## Reusable results

- [Hermes discovery](https://github.com/user01-2-GitProject/ai-command-center/blob/a9ace6cc0724fc9f68cb9491630ecb859f71f50e/docs/discovery/hermes.md), owner Claude Code session `37ad8fad-7366-46fc-b6a2-0f6e5e4d2a60`.
  Initial `d8cf87d` incorrectly suggested the HTTP server as an occupancy route;
  `68a6720` explicitly corrected it; `a9ace6c` adds compaction pressure findings.
  Retain the latest document including its appended corrections. It establishes
  the intended observe-only boundary and distinct cumulative usage versus occupancy.
  Its dated live counts are evidence from that run, not refreshed measurements.
- ACC-05 design, owner Hermes Agent / Photon session: inspect locally with
  `git show task/ACC-05-observer-chat-dashboard:docs/design/first-screen.md`
  and the adjacent `observer-chat-prototype.html`. Original screenshot artifacts
  are under `docs/design/screenshots/` at the same immutable commit.
  This is a static preview; its sample chat and local draft staging prove no provider integration.
- The three-phase `docs/completion-plan.md` and ACC-16/17 specifications exist
  only on ACC-05's local branch. Their publication correction is already preserved
  in the Library. They do not silently supersede the canonical release gates.
- No Claude Code/Codex discovery documents, architecture, runnable shell,
  adapters, or application test suite were found in any listed branch tree/history.
  This absence is bounded to the inspected project sources.

## Contradictions and action owners

| Finding | Resolution / next action | Owner |
| --- | --- | --- |
| Canonical local main is `cb43af6`; live remote main is `53d8bcc`. | Base new work on verified remote revision. Operator can fast-forward the clean canonical checkout; do not mistake old main for current specifications. | Operator |
| Plan courtesy paragraph says ACC-05 eligible/unclaimed; task note says review. | Respect task note. Do not reclaim existing delivery silently. | Operator; ACC-05 owner for review fixes |
| ACC-01/03 notes say “unmet dependencies still prevent starting” despite empty dependencies. | Template text is stale; these tasks are eligible subject to claims. Correct own task note when claimed. | Respective task owner |
| Phase 2 plan shorthand says ACC-06 after 01–04, including deferred Buzz. | Repo spec and ACC-06 note agree: ACC-01 plus at least two completed provider discoveries. Buzz is not a dependency. | ACC-06 owner/operator |
| ACC-05 adds a backend/front-end/security three-phase grouping, whereas canonical Library uses phases 0–5. | Ask Jimmy which grouping “current phase” means. Until resolved, perform discovery common to both; do not enable credential/chat work by inference. | Jimmy/operator |
| ACC-05 checklist claims full context/freshness coverage, but HTML lacks the decided pressure strip and an explicit stale measurement example. | Review must resolve missing messages-in-window/compacted/summary counts and stale sample before accepting complete design coverage. Source read is evidence of this gap; no visual acceptance claimed. | ACC-05 owner; Jimmy for visual approval |
| ACC-05 handoff says only visual approval remains, while three reference non-goal checkboxes remain unchecked. | Reviewer must check actual artifact rather than treating the handoff as acceptance. | ACC-05 reviewer |
| Old overview references a lost Hermes image-cache file. | Use committed `docs/design/reference/16bit-ops-room-reference.webp`; preserve old history. | ACC-05 owner |
| Initial Hermes HTTP occupancy suggestion and open operability question conflict with later evidence/decision. | Later correction and observe-only decision govern. Do not resurrect a dashboard-hosted agent as a telemetry workaround. | ACC-09/ACC-08 owners |
| Earlier named-worker intentions have no corresponding recovered artifacts. | Pollen/Honey/Fizz are not automatically assigned. Unlocated work remains unknown, not failed or complete. | Hermes/operator |

## Reproduction and verification

Run from any checkout sharing this repository:

```sh
git status --short
git worktree list
git branch -a
git log --all --oneline -- docs/discovery
git ls-tree -r --name-only main
git ls-tree -r --name-only task/ACC-05-observer-chat-dashboard
git show task/ACC-02-hermes-telemetry:docs/discovery/hermes.md
git show task/ACC-05-observer-chat-dashboard:docs/design/first-screen.md
git show task/ACC-05-observer-chat-dashboard:docs/completion-plan.md
git ls-remote origin refs/heads/main refs/heads/task/ACC-02-hermes-telemetry refs/heads/task/ACC-05-observer-chat-dashboard
```

All commands above were run (the initial network failure and successful retry are
recorded above). Local status was clean before changes. Artifact references were
checked with `git cat-file -e`; `git diff --check` passed for this delivery.
No application tests apply to this documentation-only recovery task.

Next: deliver ACC-01 for independent acceptance, then verify ACC-03 and
ACC-PV-codex sequentially under Jimmy's explicit 2026-09-29 instruction.
ACC-02 and ACC-05 still require separate review, and the latter Jimmy's visual
approval. No merge, deployment, provider dispatch, or credential change occurred.
