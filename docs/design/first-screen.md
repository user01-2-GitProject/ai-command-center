# ACC-05 — First dashboard screen design

Status: `review` — visual approval pending from Jimmy.
Branch: `task/ACC-05-first-screen`
Mockup: `docs/design/first-screen-mockup.html` (open in a browser; no build step)

All data in the mockup is explicitly labeled sample data. Nothing in it is live telemetry.

## Recommended design: sector board + list

One screen, two views of the same data, toggled with a single keypress:

1. **Sector board (default).** A 16-bit-inspired ops board. Each provider is a
   "sector" tile on a dark grid; each active session is a node on that tile.
   Session nodes carry an HP-style occupancy bar (context used vs. limit),
   an activity glyph (idle / working / error), and a freshness badge.
   Clicking or keyboard-selecting a node opens its detail strip: session
   identity, model, context used/limit, measurement source, updated time,
   and any error or unavailable reason.
2. **Plain list (one keypress away).** A dense, fully keyboard-navigable table
   with identical information and no decoration. This is the accessibility
   baseline and the narrow-window layout: below ~720px the board collapses
   into the list automatically.

Below the board/list sits an **activity strip**: a single merged feed of the
most recent tool calls across all sessions, newest first. Each row names
the session, the tool, the outcome, and any error — tool names, outcomes,
and errors only. No prompt text, no conversation content, ever.
(Jimmy's decision, 2026-09-29: the strip shows whatever is newest,
merged across sessions, not grouped per-session.)

The header carries the dashboard title, a LOCALHOST badge, the last-updated
clock, the view toggle, and a motion toggle. A persistent banner reads
"SAMPLE DATA — for design review only" until a live adapter is connected.

## What the screen must always show (acceptance coverage)

- Agent/session identity and activity state — node label + detail strip.
- Context used/limit — segmented occupancy bar; exact numbers in the detail
  strip.
- Measurement source — e.g. "measured via Hermes local API", "reported by
  provider", or "unknown".
- Updated time — absolute timestamp plus relative age ("12s ago").
- Stale state — data older than the freshness threshold (proposed: 60s)
  gets a STALE badge; the board node dims.
- Unavailable state — unknown model limit, unreachable source, or provider
  error each get an explicit reason string. A session with an unknown limit
  shows its used tokens but **no percentage** — percent is computed only
  from a measured used/limit pair for the same model.
- Errors — provider errors render as contained error cards naming the
  source and the failure; a failing provider never blanks the others.

## Consequential choices for Jimmy

1. **Default view: sector board, not the list.** The board gives the
   dashboard its 16-bit identity and makes multi-session state scannable.
   The list is one keypress away and is the automatic narrow-window layout.
   If you prefer density-first, we can flip the default.
2. **Occupancy as segmented HP bars, not gauges or percentages alone.**
   Bars read at a glance; exact numbers sit one selection away. Unknown
   limits render as a hatched "?" bar rather than a fake number.
3. **Freshness threshold: 60 seconds.** Older than that reads STALE.
   Backends (ACC-08) will define this properly; 60s is the design placeholder.
4. **Polling: 15s with a visible countdown and a manual refresh key.**
   Motion toggle and `prefers-reduced-motion` disable all non-essential
   animation. No auto-playing decorative effects.
5. **Read-only chrome.** No buttons that dispatch, approve, or message
   anything. The most prominent interactive elements are view switching,
   refresh, and selection.

## Deliberately not built (reference vs. guardrails)

The 16-bit ops-room reference (`docs/design/reference/16bit-ops-room-reference.webp`)
was treated as inspiration. Four of its elements were explicitly excluded:

1. **HUMAN IN THE LOOP panel (APPROVE / REJECT / MODIFY).** Approvals that
   trigger agents are deferred. The first release is read-only; the screen
   designs no control surface for dispatch.
2. **TOKEN BURN RATE / MIN gauge.** That metric is cumulative throughput,
   not context occupancy. The top-priority requirement is occupancy, so no
   burn-rate gauge stands in for the context view.
3. **AGENT LOGS / REASONING panel with prompt text.** The activity strip
   shows tool names, outcomes, and errors only. Prompt and conversation
   content never render.
4. **Confidence 88%.** No provider supplies a confidence metric. No
   component depends on an invented number.

## Accessibility and layout notes

- Full keyboard operation: `Tab` moves through regions, arrow keys move
  between session nodes/cards, `Enter` opens the detail strip, `1`/`2`
  switch views, `r` refreshes. Focus is always visible.
- Readable text: minimum 13px effective, high-contrast phosphor palette,
  no text inside the isometric decoration.
- Reduced motion: `prefers-reduced-motion` disables pulse/scan animations;
  the motion toggle in the header does the same on demand.
- Narrow window: below ~720px the board becomes the list; the detail
  strip becomes full-width. Long session names truncate with ellipsis and
  full text on focus/hover via `title`.
- Many sessions: the board paginates sectors by provider; the list
  virtualizes nothing but stays a single scroll region with sticky headers.

## Resolved questions (approved by Jimmy, 2026-09-29)

- Staleness threshold: 60s stands as the initial value (ACC-08 owns the
  final answer; providers may declare their own later).
- Sector board is the default view; plain list is one keypress away.
- Activity strip is a single merged chronological feed, newest first —
  "the correct scope is whatever is newest."
