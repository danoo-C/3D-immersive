# M3 · Phase 7 — The parameters pane, clip gain and fades

**Status:** in progress · **Plan:**
[plans/phase_7_parameters_pane.md](plans/phase_7_parameters_pane.md)

## Goal

The parameters pane replaces its placeholder and follows the selection. It
shows a channel, a clip, a media file or — with nothing selected — the
project's settings, with the fields `04` lists for each. Its fields can be
dragged and typed with units. Clip gain and fade-in and fade-out length and
shape (F-15) are edited here, and a fade's length can also be set by
dragging a handle on the clip. BPM and time signature are edited in the
project view and in the toolbar chips beside the transport. Fields that
belong to later milestones are drawn, disabled, with the milestone that
brings them.

## Scope

**In:** the four views in `04`'s *Parameters pane* table; with several
things of one kind selected, only the fields they share, reading `—` where
their values differ, and setting such a field on all of them in one edit
(`04`, *Selection*); the numeric field from phase 2, reused; clip gain,
fade lengths and fade shapes, linear and equal-power; fade handles on the
clip (the `fade handle` group); BPM and time signature as undoable project
edits, from the pane and from the toolbar chips, the grid moving under
unchanged material (D-52); the media view's full waveform and its audition
button, deferred here by M2; the pane collapsing to a strip (`04`); the
input groups `04` lists under M8 that this is the first to draw — spin box,
check box, combo box.

**Out:** position fields → M5. Pan → M4, with the bypass path. HRTF set,
distance rolloff, master gain and the limiter → M4. All of these are drawn
disabled. Snap override editing is already on the header, from phase 5, and
the pane shows the same value.

## Acceptance

- [ ] With a clip selected, the pane shows its source, start, length, crop
      offset, gain and both fades; changing any of them is one undoable edit,
      and the clip in the timeline follows.
- [ ] With several clips selected, a field whose values differ reads `—`,
      and setting it sets it on all of them in one edit.
- [ ] Dragging a clip's fade handle sets that fade's length in one command
      on release; a fade never exceeds its clip, and the two fades together
      never overlap.
- [ ] A channel's view edits its name, colour, gain, mute, solo, bypass and
      snap override; its position and pan fields are there, disabled, saying
      which milestone brings them.
- [ ] With nothing selected, BPM and time signature are editable, each one
      undoable edit, and the toolbar chips show and edit the same values.
      Changing the BPM moves the grid and no clip (D-52).
- [ ] A media file selected in the pool shows its path, source rate,
      channels, duration and full waveform, and its audition button plays
      it.
- [ ] Typed values take units — `-6 dB`, `1.5 s`, `2.1.000` — and a value
      out of range does what the plan decides and says so.
- [ ] The new groups are in `04`'s vocabulary table and the bundled theme,
      moved out of M8's row; no widget in the pane names a hex.
- [ ] A screenshot of each view is taken and looked at.

## Implements

F-15, F-16 (BPM and signature), D-52, D-57 — *Parameters pane*,
*Selection* and *The vocabulary grows* in
[04-ui-spec.md](../04-ui-spec.md), `Clip` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
