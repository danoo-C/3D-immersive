# Plan — M3 · Phase 7 — The parameters pane, clip gain and fades

**Written:** 2026-09-26 · **Status:** in progress

## Approach

Three layers, as in the phases before. **What an edit does belongs to
`core`.** Two new clip edits, a length and a slip, work out their limits as
a trim does. Fades gain a rule that `validate()` holds (D-101), so no edit,
whichever widget made it, can leave two fades overlapping. Setting a field
on several things is a `Compound` of `SetAttribute`s, one Undo.

**What a field shows and accepts is a Qt-free format.** `units.py` grows
from "a number and a unit" to a small set of formats: gain in dB, a
duration in seconds or milliseconds, a position in bars.beats.ticks or
minutes:seconds, and a tempo. Each shows a value and parses what a person
types. `NumericField` takes a format rather than a bare unit, and learns to
read `—` when the selection's values differ. Phase 9's playhead readout is
the next field to need the position format.

**The pane is one widget, `ui/parameters/`, that follows the selection.**
It builds the view for the selection's kind, or for the project when
nothing is selected. After every change the document reports it reads the
values back in place, and rebuilds only when the kind changes, so a value
being typed is not thrown away by an edit elsewhere. That is the header
column's rule from phase 2. Every field commits through the document as
one command.

The alternative was a form per view built from a table of field
descriptions, generic over the model. It was rejected: the four views
share almost nothing but the numeric field, and several fields behave
unlike the rest (a start that moves the selection, a length that trims, a
disabled field that names a milestone). A table would need an escape hatch
for most of its rows.

## Decisions settled here

**Two fades never overlap (D-101).** `validate()` refuses a fade longer
than its clip, and two fades together longer than the clip. A trim that
leaves too little room shortens the fade on the edge it moves, and the
other only if that is not enough. A fade that is dragged or typed stops
where the other begins. Until now each fade was cut to fit on its own, so
a trim could already make an overlap, and nothing could see it.

**Several clips in the pane (D-102).** The start is the selection's
start, the earliest, and typing one moves the whole selection as a drag
does. Length, crop offset, gain and the fades are each clip's own. Values
that differ read `—`, and a typed value goes to each clip as far as that
clip can take it. The source is shown, not edited. The acceptance's
"changing any of them" is read as the fields that can be changed, since
nothing in the specification replaces a clip's sample.

**Positions in the ruler's unit, durations in seconds (D-103).** A start
reads as the ruler does. Length and crop offset read `1.500 s`, fades
`250 ms`, and all three take either unit.

**Tempo and signature ranges (D-104).** 20 to 999 BPM to one decimal;
1 to 32 beats of a 1, 2, 4, 8 or 16 note.

**What "a value out of range does, and says so".** It lands as far as it
can, and the field then shows the value it landed on, read back from the
project. The numeric field already clamps to its own range and shows the
clamped value; what is new is that a clip's limits are the clip's (its
sample, its neighbour, its other fade), and so they are worked out by the
edit rather than by the field. A typed value that changes nothing at all
puts the old value back.

**A field reading `—` is typed into, not dragged.** A drag has no value to
start from, and starting from the first selected thing's would be
arbitrary. A press opens it for typing.

**With several channels, the name reads `—` and is disabled.** Giving
several channels one name has no use, and doing it by accident loses every
name but one, which Undo alone would bring back.

**Fade handles are grabbed in the name strip.** A selected clip shows a
small square handle at the top of each fade, at the fade's end. The strip
along the top of the clip is where a press near a handle takes the handle.
Below the strip, a press near an edge still trims, as in phase 5. Ableton
places them the same way. A handle drag changes the same fade of every
selected clip by the same amount, each as far as it can, as a trim does
(F-51). It edits nothing until the release, and `Esc` puts it back.

**The toolbar's tempo becomes a field and the signature a menu.** The BPM
chip becomes a numeric field, dragged or typed. The signature chip becomes
a button whose menu offers the common signatures (2/4, 3/4, 4/4, 5/4, 6/8,
7/8, 12/8). Anything else is set in the pane. The chip, like the snap
chip, stays out of the focus chain.

**The pane collapses to its header.** Clicking the header hides the body
and gives the room to the pool; clicking it again brings the body back.
Not remembered across sessions: that is M8's session persistence.

**The input groups.** The pane is the first to draw a spin box (the
signature's beats), a check box (mute, solo, bypass and the limiter) and a
combo box (fade shapes, the signature's note, the HRTF set). Each gets a
group in the bundled theme and a row in `04`'s table, moved out of M8's.

## Steps

1. **Fades that fit, and the edits the pane needs, in `core`.**
   `validate()` holds D-101. `_piece_to` fits both fades, the moved edge's
   giving way first. `fade_room()` says how long a fade may be.
   `SetLengths` trims each clip's end to a length, as far as it can, and
   `SlipClips` moves each clip's offset within its sample.
   *Test (headless):* a trim through two long fades shortens the moved
   edge's first, and the other only when it has to; a split and a drop
   leave valid fades; `validate()` names an overlap and a fade longer than
   its clip; a length stops at the neighbour and at the sample's end, and
   is one Undo for several clips; a slip stops at the sample's ends and
   leaves start and length alone; the random runs gain fades, lengths and
   slips, and stay valid.

2. **Fields in any unit, and a field that reads `—`.** The formats in
   `units.py`: gain, duration, milliseconds, position (bars or time, read
   against the project's tempo when shown and parsed) and tempo.
   `NumericField` takes a format and a `set_mixed()`. The spin box, check
   box and combo box groups go in the theme file and the stylesheet.
   *Test (headless for the formats):* each format round-trips what it
   shows; `2.1.000`, `0:02.5`, `1.5 s` and `250 ms` parse to the right
   samples at 120 and at 90 BPM; nonsense is refused. *(gui):* a mixed
   field reads `—`, is typed into on a press, and commits what was typed;
   Esc puts `—` back; the new groups are read by the stylesheet and pass
   the contrast rule.

3. **The pane, following the selection.** `ui/parameters/pane.py` replaces
   the placeholder: a view per kind, rebuilt only when the kind changes,
   read back in place after every change, and collapsing to its header.
   The project view: BPM, signature, and the M4 fields disabled with their
   milestone. The toolbar's BPM field and signature menu.
   *Test (gui):* the view follows the selection's kind; a value being
   typed survives an edit elsewhere; BPM and signature from the pane and
   from the toolbar are each one Undo, and the other shows the change; a
   BPM change moves no clip (D-52) but moves the grid; the disabled fields
   name M4; collapsing hides the body and gives its room to the pool.

4. **The clip view, and several clips at once.** Source, start, length,
   crop offset, gain, and each fade's length and shape.
   *Test (gui):* each field is one Undo and the clip in the timeline
   follows; with several clips, differing values read `—` and a typed one
   goes to all as far as each can; the start moves the selection and keeps
   its shape; a length past the neighbour lands at the neighbour and the
   field shows it; a fade past the other fade stops there.

5. **The channel and media views.** The channel's name, colour, gain,
   mute, solo, bypass and snap override, with position disabled for M5 and
   pan (shown only while bypassed) for M4. The media file's path, rate,
   channels, duration, full waveform and audition button.
   *Test (gui):* each channel field is one Undo and the header follows,
   and the reverse; several channels take a gain as one edit and their
   name is disabled; the media view shows its waveform once peaks arrive,
   and the button auditions, or says why it cannot.

6. **Fade handles on the clip; written down, and looked at.** Fades drawn
   in the clip. Handles on selected clips, grabbed in the name strip; a
   drag previewed and pushed on release. `04`'s *Parameters pane*,
   *Timeline* (fades and handles), and the vocabulary (`clip`'s fade keys
   and the three input groups). A grab of each view and of a fade drag.
   *Test (gui):* a handle drag sets the fade in one command on release,
   stops at the other fade and at the clip's length, and changes the same
   fade on every selected clip; `Esc` puts it back; a press in the strip
   near a handle takes the handle and below it still trims.

## Files

```
docs/01-requirements.md                     amended — four decisions
docs/02-architecture.md                     amended — ui/parameters/
docs/03-data-model.md                       amended — Rules: fades
docs/04-ui-spec.md                          amended — the pane, fades, groups
docs/doc-system.md                          amended — high-water mark
src/immersive/core/model.py                 amended — validate(): fades
src/immersive/core/edits.py                 amended — fitting fades, SetLengths, SlipClips
src/immersive/ui/units.py                   amended — formats
src/immersive/ui/widgets/numeric.py         amended — a format, and `—`
src/immersive/ui/parameters/__init__.py     new
src/immersive/ui/parameters/pane.py         new — follows the selection
src/immersive/ui/parameters/views.py        new — the four views
src/immersive/ui/timeline/clips.py          amended — fades and handles drawn
src/immersive/ui/timeline/dragging.py       amended — a press on a handle
src/immersive/ui/timeline/view.py           amended — the handle drag
src/immersive/ui/main_window.py             amended — the pane, the chips
src/immersive/assets/app.qss                amended — spin, check, combo
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — the same, and clip's fade keys
tests/test_edits.py                         amended
tests/test_model.py                         amended — fades validated
tests/test_units.py                         amended — formats
tests/test_numeric.py                       amended — `—`
tests/test_parameters.py                    new — gui
tests/test_fade_handles.py                  new — gui
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A saved file with overlapping fades refused on open | a project that opened yesterday does not open today | no edit could make one before this phase, and none will after; only a hand-edited file could. `validate()`'s refusal names the clip, as for every other rule |
| The pane rebuilt under a value being typed | an edit elsewhere throws away what someone is typing | read back in place; rebuilt only when the selection's kind changes; tested with an edit landing mid-typing |
| A pane field and the header disagreeing | two places showing a channel's gain with different values | both read the model after every change the document reports; a test edits in each and reads the other |
| The fade handle's zone stealing the trim's | a clip's corner becomes impossible to trim | handles only on selected clips and only in the name strip; a test presses in the strip and below it at the same x |
| Equal-power drawn wrong | a curve that does not match what phase 8 plays | the drawn curve is computed by one Qt-free function that phase 8's engine can call too |
| The pane's fields taking the toolbar's first focus, as the snap chip did | the window opens with a ring around the tempo | the tempo field and signature button are kept out of the focus chain; a test holds the window's first focus |
| A format that reads the tempo when built | a start shown in the old tempo's bars after a tempo change | the position format asks the project for its tempo each time it shows or parses |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| `validate()` not checking the fades' sum | an overlap a trim made goes unrefused |
| the fade on the edge not moved giving way first | a trim shortens the untouched edge's fade |
| both fades cut in proportion | neither edge keeps what it had |
| a length that passes the neighbour | an overlap, refused by validation |
| a slip past the sample's end | `offset + length` past the frames |
| a slip that moves the start | the clip jumps along the timeline |
| the position format reading the tempo once | a start in the old tempo's bars |
| a duration parsed as bars | `1.5 s` becomes a bar and a half |
| a mixed field scrubbed from zero | a drag sets every clip to a value near 0 |
| the pane rebuilt on every change | a value being typed is lost |
| several clips' start set on each | clips on one lane overwrite each other |
| a field set on the first selected clip only | the rest keep their old value |
| a multi-field edit as several commands | several Undos for one field |
| a BPM change moving clips | D-52 broken |
| the toolbar chip not reading back a pane edit | two tempos shown |
| the name editable for several channels | every channel renamed alike |
| a disabled field not naming its milestone | a dead control with no reason |
| a handle drag pushing on every movement | many Undos for one drag |
| a handle taking a press below the strip | the corner cannot be trimmed |
| a handle drag moving one clip's fade only | F-51 broken |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Hearing gain and fades | phase 8, the engine |
| A handle for clip gain on the clip itself | not planned; gain is set in the pane. Raised if missed |
| Replacing a clip's sample | not planned (D-102) |
| Position and pan fields made live | M5 and M4 |
| The pane remembering whether it was collapsed | M8, session persistence |
| Fade curves beyond linear and equal-power | not planned; F-15 names none, and `03` names these two |

## Outcome

Filled in at the end.
