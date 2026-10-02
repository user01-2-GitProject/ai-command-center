# Handoff — ACC-12 isometric sector rework

- Task ID / agent / session / UTC date: ACC-12 (visual rework) / iggy / main chat / 2026-09-29
- Scope completed: Rebuilt the dashboard's sector board as a
  canvas-rendered isometric ops room per Jimmy's direction ("it's
  supposed to look like this", pointing at
  `docs/design/reference/16bit-ops-room-reference.webp`). Diamond tile
  floor, back walls with server racks (blinking lights), glowing data
  paths, hand-authored 12x14 pixel robot sprites per session (provider
  colors; working bob; dimmed stale; red ? marker), click + arrow-key
  selection, window chrome (title bars with _ ▢ X) on every panel.
  Bottom strip is honest data only: CONTEXT LOAD (per-session occupancy
  bars) and PROVIDERS (status pills) instead of the reference's burn
  gauge. Read-only scope kept: no approve/reject/modify, no
  reasoning/log text — those need a real action queue and reasoning
  APIs that don't exist yet.
- Files and commit/PR (or exact local artifact paths):
  - Branch `task/ACC-12-isometric-sector`, commit `f05a8e7`
    "ACC-12: isometric sector room per the visual reference" (no push;
    GitHub CLI not authenticated).
  - Changed: `app/ui/index.html`, `app/ui/app.js`, `app/ui/style.css`.
  - Art iterated via `/tmp/iso_preview.py` (PIL) before porting to canvas.
- Checks actually run and observed results:
  - `node --check app/ui/app.js` — OK; sprite rows asserted 12 wide.
  - `python3 -m unittest discover -s app/tests` — 22/22 pass (backend untouched).
  - Interactive widget preview shown to Jimmy in chat (demo payload).
- Acceptance criteria still unchecked:
  - Screenshots: no browser can render the page here; visual QA done
    via PIL art previews + the in-chat widget.
  - Jimmy's visual sign-off on the new look (pending his reply).
  - Real adapters still pending discovery on his machine.
- Limitations and blocked reason, if any:
  - Library inaccessible; no canonical claim. No push/PR without
    Jimmy's approval + GitHub auth.
- Exact next action: Jimmy reviews the isometric preview; if he wants
  the HITL approve/reject panel or logs text back, spec the required
  backend (action queue + dispatch; reasoning APIs) first — do not fake
  them. Otherwise operator reviews/merges the branch.
- Review outcome / reviewer / integrated revision (filled at acceptance):
  pending.

## 2026-09-29 17:30 EDT — Jimmy's window correction

Jimmy: "instead of a floating platform it should be a literal window (not
a microsoft one) into the 'robot room'... it should be huge, when i turn
my phone sideways it should consume about 45% of the screen the way the
mockup does."

Changes on `task/ACC-12-isometric-sector` (unpushed):
- Sector title bar (_ [] X) removed; the sector is now a window FRAME with
  live "ROBOT ROOM" tag + session count overlays — no OS-window chrome.
- Canvas cover-scales an adaptive scene: far wall + server racks pin to the
  top of the visible rect, floor tiles bleed to every frame edge, dark
  near-wall wedges at the bottom corners + vignette for glass feel.
- Layout mirrors the reference proportions: sector is the dominant
  element (~45% of screen area), activity/detail right column, context
  load + providers bottom strip.
- Session slots recomputed for maximum spread (min 107px pairwise, no
  label-band collisions); labels 8px truncated to 12 chars.
- ResizeObserver refits backing store; verified via PIL mirror + 22/22 tests.

## 2026-09-29 17:55 EDT — Jimmy's mobile sizing

Jimmy (on iPhone): 50vh was "a bit big" — the robot window should be a
floating tile taking the entire screen width, at about 40% of the 50vh
height, i.e. ~20vh. Mobile layout now: full-bleed tile on top, panels
scroll below. Camera top-pins short viewports (dy0=70) so session labels
never clip; portrait keeps fit-room-width.

## 2026-09-29 ~18:10 EDT — per-agent follow-cam windows (mobile)

Jimmy: push the tile all the way to the screen edges (widget-only CSS now
bleeds -16px past the chat padding; border kept), and "make a window for
each specific agent that the camera will follow".

- Mobile now renders one window per agent (plus one per errored provider).
  Each tile's camera eases toward its robot at 1.35x zoom and follows it;
  robots wander gently near their home slots when motion is on.
- Tiles are full-width, 20vh, thin border, name + status dot tag; tapping a
  tile selects the session and shows its detail panel below.
- Desktop keeps the single wide room window. drawRoom() is shared by both.

## 2026-09-29 ~23:30 EDT — iggy operator robot
- Generated iggy robot character art (beige fluffy robot, gold glow eyes,
  burgundy/gold #21 jersey, matching headphones) + animated idle loop.
- Assets: app/ui/assets/iggy-robot.webp (master), iggy-robot-256.webp
  (runtime, 9.3KB), iggy-robot-loop.mp4 (animation).
- app/ui/app.js: iggy drifts around the room as a circular gold-ringed
  medallion portrait labeled IGGY (drawImage, smoothing on for the art).
- Hardened drawRoom: null payload no longer kills the rAF loop when the
  first fetch fails.
- Verified: node --check, DOM-stub harness (zero errors, full demo path),
  python unittest 22/22.

## 2026-09-29 ~23:45 EDT — iggy grounded isometric sprite
- Jimmy: carpet monsters can't fly. Retired the floating medallion portrait.
- New asset: app/ui/assets/iggy-robot-iso.png (75x112, 20KB, magenta keyed
  to transparent) — 16-bit isometric pixel-art iggy robot, grounded.
- app/ui/app.js: iggy now walks the room on the floor like the session
  robots (shadow ellipse, gentle bob, IGGY label), drawn slightly larger
  (50x75) with smoothing for the downscale.
- Verified: node --check, DOM-stub harness zero errors (raw + demo paths),
  python unittest 22/22.

## 2026-09-30 ~21:55 EDT — fluffy iggy takes over the room
- Jimmy: "you'll look better regular in the dashboard." Retired the robot
  sprite; the operator is now the classic fluffy carpet-monster iggy.
- New asset: app/ui/assets/iggy-iso.png (82x112, 20KB, magenta keyed to
  transparent) — 16-bit isometric pixel-art fluffy iggy, grounded.
- New reference: ~/workspace/avatars/saved/iggy-char-sheet-fluffy.webp —
  9-pose claymation model sheet (turnaround, expressions, actions).
- Verified: node --check, DOM-stub harness zero errors (raw + demo),
  python unittest 22/22.
