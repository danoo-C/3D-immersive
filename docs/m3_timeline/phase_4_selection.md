# M3 · Phase 4 — Selection

**Status:** ✅ complete · **Plan:**
[plans/phase_4_selection.md](plans/phase_4_selection.md)

## Goal

Clips, channels and media files can be selected: one kind at a time, as
many of that kind as wanted (D-57). Clicking, Shift+click, Ctrl+click and a
rubber band over empty lane space select clips across channels. Clicking a
header selects a channel, and a pool row is a media selection. `Ctrl+A`
selects every clip on the focused channel, then every clip in the project.
The selection lives in `core`, where every edit that takes a selection can
read it and a test can reach it without a window.

It comes before the edit verbs because every one of them acts on it (F-51).

## Scope

**In:** `core/selection.py`, the selection model planned in
[02](../02-architecture.md), observed by the UI without Qt; the three kinds
M3 has — clips, channels, media files — with keyframes left to M6; each way
of selecting in `04`'s *Selection* table; switching kind clearing the
previous kind; clearing by clicking empty space or pressing `Esc`; what
happens to a selected clip that an undo removes; the `clip selected border`
group; `B` toggling bypass on every selected channel; the pool's rows joining
the same selection rather than keeping one of their own.

**Out:** anything done to the selection → phase 5 and phase 6. The
parameters pane that follows it → phase 7. `Esc` meaning *stop* while the
transport runs → phase 9. Keyframe selection → M6.

## Acceptance

- [x] Clicking a clip selects it alone, and Shift+click and Ctrl+click
      extend and toggle as `04`'s *Selection* table says.
- [x] A rubber band over empty lane space selects every clip it touches,
      across channels.
- [x] Selecting a channel clears any clip selection and the reverse, and
      selecting a pool row clears both (D-57).
- [x] `Ctrl+A` selects every clip on the focused channel, and pressed again
      every clip in the project.
- [x] Clicking empty space, or `Esc`, clears the selection.
- [x] A selected clip removed by an undo leaves the selection, and nothing
      else in it changes.
- [x] `B` toggles bypass on every selected channel as one command, and its
      tooltip no longer names M3.
- [x] The selection is tested headless: `core/selection.py` imports no Qt,
      which `test_layering.py` already enforces for everything in `core/`.
- [x] A selected clip is marked by the `clip selected border` group, which
      is in `04` and the bundled theme, and by more than colour alone.

## Implements

F-51, D-57 — *Selection* and *Keyboard* in
[04-ui-spec.md](../04-ui-spec.md), the planned `selection.py` in
[02-architecture.md](../02-architecture.md).

## Notes

Appended while building.

**The selection is the document's (D-96), and the prune is the only thing
that forgets.** After every change, before any observer is told, it drops
whatever is no longer in the project, by identity. New and Open need no
clear of their own: a fresh project holds none of the old things, so the
same prune empties it. The clear the plan put there was taken out when its
mutation turned out to be one no test could tell apart.

**A press on a selected clip waits for the release.** It leaves the
selection alone so that phase 5 can drag every selected clip from any of
them, and a release that never moved selects that clip alone. Built now,
so a click does not change its meaning when dragging arrives.

**A range that only grows cannot tell adding from replacing.** Twice a
mutation turning Shift's *replace* into *add* survived, once for clips and
once for headers, because what was selected before the Shift+click lay
inside the range, and adding the range gave the same answer as replacing
with it. Both tests now leave something outside the range first, so the
range has something to throw out.

**The pool's tree keeps a selection of its own, because Qt insists.** It
is kept in step both ways: a row picked becomes a media selection, and
every change to the document's selection, and every rebuild, sets the
tree again. A guard stops that setting from echoing back as a choice; a
mutation that dropped the guard around a rebuild lost the selection on the
next edit, and was killed.

**A selected header wears a bar, and the bar's room is always there.**
Every header carries a 3 px transparent left border, which selection
colours, so the controls in it do not shift by three pixels when it is
clicked.

**`Ctrl+A` in a line edit can only be tested as a claim.** Offscreen no
window is active, so no shortcut fires in a test at all. What is held is
that the rename field accepts the shortcut override for `Ctrl+A`, which is
what keeps Edit › Select All from seeing it, and selects its text.

**Looked at:** clips selected on four lanes, a band dragged across three,
two channels selected. The border reads on every lane, but on the first
channel it is weakest: that channel's palette colour is `accent`, so its
selected clip is purple on purple, told apart by the full frame, where an
unselected clip shows only its right edge, and by the border being solid
over a translucent body. `04`'s example names `accent`, so it stays; a
theme can move it with `clip.selected.border`.

The phase adds 43 tests. The suite is 1617: 14.5 s serially, 5.5 s in
parallel, 3.2 s in the fast lane.
