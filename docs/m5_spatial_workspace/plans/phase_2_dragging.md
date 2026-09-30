# Plan — M5 · Phase 2 — Dragging, heard

**Written:** 2026-09-30 · **Status:** in progress

## Approach

**A drag is heard before it is an edit (D-144).** While a source is dragged,
where it would be if the drag ended now is held by `Placing`, a small
Qt-free object the window shares with both views, the pane and the feed:

- the **views** draw the channel being placed from it, not from the model,
  so the icon follows the pointer in both views at once;
- the **feed** sends the engine the placed position at each movement, one
  `POSITION` command a side through the ring (D-121), so it is heard at the
  next block. It records what it sent as what the engine has;
- the **pane**'s position fields show it, so they follow the drag.

The release asks `Placing` for the one edit the drag makes and pushes it:
one edit, one undo step (02, *Undo*). The model changes once, so neither
`validate()` nor every document observer runs at the rate the mouse moves.
The feed then finds the engine already where the edit puts it, and sends
nothing. Esc drops the drag, and the feed sends the model's position back.

**The side grabbed leads (D-145).** A channel's one point moves as dragged.
A pair is dragged by either side. For a linked pair, the other side follows
in its mirror about the pivot, and the edit stores the left side, which is
the mirror of the right, since the mirror is its own inverse (D-132). For a
free pair, the side grabbed moves alone: the left is `position`, and the
right is `placement.right`. These are the edits the pane already makes for a
typed side.

**A drag in a view.** A press on an icon selects its channel, as a click
does. Once the pointer has moved 4 px, the drag begins. Each movement then
puts the grabbed side under the pointer, keeping the offset at which it was
grabbed so the icon does not jump. The top view sets X and Y and the front
view X and Z, and the third axis is left where it was. Only the channel
grabbed moves. Dragging several selected channels together waits until it
is asked for.

## Decisions settled here

**D-144**: a drag is heard before it is an edit, through a shared
`Placing`, and makes one edit at its release. **D-145**: a pair is dragged
by either side, and the side grabbed leads.

## Steps

1. **`Placing`.** `ui/spatial/placing.py`, Qt-free. Tests: the sides placed
   for a point, a linked pair grabbed by either side, and a free pair
   grabbed by either side; the edit each makes at the end, and undoing it;
   Esc making none; observers told of each move.
2. **The feed's preview.** `Feed.preview`. Tests: a placed position is sent
   as `POSITION` commands, both sides of a pair; the edit that follows sends
   nothing more; a cancel sends the model's position back.
3. **Dragging in the views.** Press, move past 4 px, release, and Esc; the
   offset kept; both views drawing the placed sides. Tests: a drag in each
   view moves only its two axes, by the metres moved; the other view shows
   the move before the release; one edit and one undo; Esc leaves the model
   as it was; a click without moving only selects.
4. **In the window.** One `Placing` for the views, the pane and the feed.
   Tests: the pane's fields show the drag as it goes; while playing, the
   engine has the new position before the release, and the document has no
   new edit until it.
5. **Looked at, the sweep and the close.**

## Files

`src/immersive/ui/spatial/placing.py` — new
`src/immersive/ui/spatial/ortho_view.py` — dragging
`src/immersive/audio/feed.py` — `preview`
`src/immersive/ui/parameters/pane.py`, `views.py` — the placed sides shown
`src/immersive/ui/main_window.py` — one `Placing`, and the feed told
`tests/test_placing.py`, `tests/test_dragging_sources.py` — new;
`tests/test_feed.py` — extended

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | a linked pair's other side not mirrored | a linked pair grabbed by its left |
| 2 | a linked pair grabbed by its right storing the right as the left | grabbed by its right: the edit stores the mirror |
| 3 | a free pair's right written to `position` | a free pair grabbed by its right |
| 4 | the edit made at every move | one edit and one undo |
| 5 | no edit at the release | the release makes an edit |
| 6 | Esc making the edit anyway | Esc leaves the model as it was |
| 7 | the top view setting Z | a drag moves only its two axes |
| 8 | the grab offset lost, so the icon jumps | a drag moves by the metres moved |
| 9 | a drag begun by a click | a click without moving only selects |
| 10 | the preview not sent to the engine | the engine has it before the release |
| 11 | a pair's preview sending one side | both sides of a pair sent |
| 12 | a cancel not sending the model's position back | a cancel sends it back |
| 13 | the other view drawing the model during a drag | the other view shows the move |
| 14 | the pane showing the model during a drag | the pane's fields show the drag |

## Risks and unknowns

- **Two things now say where a source is**, the model and `Placing`. That
  is only true during a drag, and only for the channel dragged. Every
  reader asks `Placing` first for that channel, and it is cleared at the
  release, at Esc and on any edit made from elsewhere.
- **Mouse tests offscreen.** `QTest` presses and moves a widget without a
  window manager, which the timeline's drag tests already rely on.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Dragging several channels at once | later, if asked for |
| Dragging the pivot | later, if asked for; typed in the pane today |
| Recording a drag as automation | M6 |

## Outcome

Filled in at the end.
