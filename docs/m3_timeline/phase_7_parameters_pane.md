# M3 · Phase 7 — The parameters pane, clip gain and fades

**Status:** ✅ complete · **Plan:**
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

- [x] With a clip selected, the pane shows its source, start, length, crop
      offset, gain and both fades; changing any of them is one undoable edit,
      and the clip in the timeline follows.
- [x] With several clips selected, a field whose values differ reads `—`,
      and setting it sets it on all of them in one edit.
- [x] Dragging a clip's fade handle sets that fade's length in one command
      on release; a fade never exceeds its clip, and the two fades together
      never overlap.
- [x] A channel's view edits its name, colour, gain, mute, solo, bypass and
      snap override; its position and pan fields are there, disabled, saying
      which milestone brings them.
- [x] With nothing selected, BPM and time signature are editable, each one
      undoable edit, and the toolbar chips show and edit the same values.
      Changing the BPM moves the grid and no clip (D-52).
- [x] A media file selected in the pool shows its path, source rate,
      channels, duration and full waveform, and its audition button plays
      it.
- [x] Typed values take units — `-6 dB`, `1.5 s`, `2.1.000` — and a value
      out of range does what the plan decides and says so.
- [x] The new groups are in `04`'s vocabulary table and the bundled theme,
      moved out of M8's row; no widget in the pane names a hex.
- [x] A screenshot of each view is taken and looked at.

## Implements

F-15, F-16 (BPM and signature), D-52, D-57 — *Parameters pane*,
*Selection* and *The vocabulary grows* in
[04-ui-spec.md](../04-ui-spec.md), `Clip` in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**Four decisions before any code.** Two fades never overlap, and a trim
shortens the moved edge's fade first (D-101). Several clips' start is the
selection's, and a typed one moves them all (D-102): setting one start on
every clip would have made clips on one lane overwrite each other. A
position reads in the ruler's unit and a duration in seconds, since a
duration in bars.beats.ticks is ambiguous (D-103). Tempo runs 20 to 999
BPM, and the signature is 1 to 32 beats of a 1, 2, 4, 8 or 16 note (D-104).

**A trim could already make overlapping fades.** Each fade was cut to fit
its clip on its own, so a 700-sample clip could keep a 600- and a
300-sample fade. Nothing could see it until fades became editable. A test
asserted that result; `validate()` now refuses it, and the trim fits both.

**The source is shown, not edited.** The acceptance's "changing any of
them" is read as the fields that can change. Nothing in the specification
replaces a clip's sample; a sample is pointed at another file from the pool
(D-90).

**No spin box.** The style draws a spin box's arrows in a colour no sheet
reaches, black on this panel, and the sheet's border triangles render as
bars in Qt. The signature's beats became a numeric field like every other
number, and the spin-box group stays with M8. **The check box paints
itself**, from a painted `check` group: styling its indicator in the sheet
loses the tick, and the style's own draws an unchecked box nearly invisible
and a disabled one like an enabled one.

**Fades are drawn by the function the engine will play**, `FadeShape.gain`,
so phase 8 cannot draw one curve and play another. The equal-power curve is
a quarter sine, and a test holds two of them crossed to constant power.

**Looked at, each view, and a fade drag.** The fade lengths were squeezed
to a sliver by the shape box, and the form was a few pixels wider than the
250 px column. A path with no spaces ran past the pane's edge. A fade of
1000 ms read `000 ms`, because a line edit keeps its cursor at the end. All
four are fixed. The handle sits over the start of a clip's name, as
Ableton's does.

**What it costs.** A window takes about 27 ms longer to build, measured
with the pane and with a placeholder in its place: 84 ms against 56. Most
of it is the stylesheet applied to the pane's thirty widgets. In the
application that is once, at startup. In the suite, where nearly every GUI
test builds a window, it is most of the serial run's growth. It belongs to
[the test-speed plan](../user-issues/tests-speeds.md), not here.

The phase adds 163 tests. The suite is 1939: 27.9 s serially, 8.3 s in
parallel, 3.7 s in the fast lane.
