# M4 · Phase 7 — The spatial fields

**Status:** not started · **Plan:** not written yet

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

- [ ] Typing a channel's X, Y or Z is one edit, undoable, and the engine
      plays the channel from there at the next block, with the crossfade.
- [ ] With several channels selected, a position field that differs reads
      `—`, and a value typed there goes to all of them in one edit.
- [ ] A bypassed channel's position fields are greyed and say why, and its
      pan field shows. A spatial channel's pan is hidden.
- [ ] The project's rolloff, master gain and limiter are live, one edit
      each, and heard at the next block.
- [ ] No field in the pane names M4 or M5 any more, and the HRTF set's
      tooltip names M8 for choosing another.
- [ ] A screenshot of the channel view with a position set, and of the
      project view, is taken and looked at.

## Implements

The *Channel* and *Nothing* rows of *Parameters pane* in
[04-ui-spec.md](../04-ui-spec.md); `Position`, `Distance`, `Master` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
