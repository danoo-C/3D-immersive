# M4 · Phase 7 — The spatial fields

**Status:** ✅ complete · **Plan:** [plans/phase_7_spatial_fields.md](plans/phase_7_spatial_fields.md)

## Goal

The parameters pane's spatial fields go live. A channel's position X, Y and
Z (moved here from M5), greyed while it is bypassed; its pan, shown only
while it is bypassed; and the project's distance rolloff, master gain and
limiter. Each change is one edit, heard at the next block. The HRTF set
field names the built-in set and says where choosing another arrives (M8).

## Scope

**In:** the fields, several channels at once by the pane's rules (`—` where
they differ); each change as one undoable edit that the feed turns into
what the engine needs; positions in metres, with the listener at the origin
facing +Y (03); the tooltips that named M4 and M5 for these fields, gone.

**Out:** dragging positions on a view → M5. Choosing another HRTF set → M8.

## Acceptance

- [x] Typing a channel's X, Y or Z is one edit, undoable, and the engine
      plays the channel from there at the next block, with the crossfade.
- [x] With several channels selected, a position field that differs reads
      `—`, and a value typed there goes to all of them in one edit.
- [x] A bypassed channel's position fields are greyed and say why, and its
      pan field shows. A spatial channel's pan is hidden.
- [x] The project's rolloff, master gain and limiter are live, one edit
      each, and heard at the next block.
- [x] No field in the pane names M4 or M5 any more, and the HRTF set's
      tooltip names M8 for choosing another.
- [x] A screenshot of the channel view with a position set, and of the
      project view, is taken and looked at.

## Implements

The *Channel* and *Nothing* rows of *Parameters pane* in
[04-ui-spec.md](../04-ui-spec.md); `Position`, `Distance`, `Master` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**Built (2026-09-27).** Every field the M3 pane drew dead for M4 and M5 is
live but the HRTF set, which shows "SADIE II D1" from the registry and
names M8. A position edit is a new `Position` per channel, made with
`replace`, since one changed in place would change what undo puts back: a
mutation doing that was caught by the undo. Several channels take a position
on the axis typed, each keeping its other two (D-127). Rolloff, master gain
and the limiter are set on the project's own `Distance` and `Master`. The
pane's three copies of "one edit or a compound of them" became one helper,
`together`.

Heard, not only edited: `tests/test_fields_heard.py` prepares `test_spatial`'s
synthetic head as the window prepares SADIE, types into the pane, and listens.
A position at +X is louder on the right from the next block, a pan hard left
silences the right, −6 dB of master gain is −6 dB out, rolloff 2 at 2 m is
half of rolloff 1, and the limiter switched off lets 1.5 through. The master
gain field keeps one decimal, so −6.0206 typed is −6.0 dB: the test's first
draft expected the finer value.

Looked at, offscreen, one channel with a position, two whose X and Z differ
(`—`, with the Y they share), a bypassed one (position greyed, pan −0.35),
and the project view. At the window's default height the pane is short, and
a channel's position sits one scroll below the bypass box. That is the pane's
existing layout, and it is resizable. The views are where a position is
meant to be set, at M5.

Twelve mutations, all caught: the plan's eleven, and the set shown by its id.
The phase adds 12 tests; the suite is 2404.
