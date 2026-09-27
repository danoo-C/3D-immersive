# Plan — M3 · Phase 5 — Editing clips, and snapping

**Written:** 2026-09-26 · **Status:** ✅ complete

## Approach

Three layers, as phase 3 had them. **What an edit does is `core`'s**: five
commands — move, trim, split, duplicate, delete — each working out
everything it will change at construction, as `DropClips` does, so `do()`
and `undo()` only apply one list of placements or the other. Every rule
about overlaps, a sample's bounds and a clip's shortest length lives there
and is tested without a window.

**Where a drag lands is a Qt-free module's**, as `landing.py` is for a drop
from the pool: which part of a clip a press took, and where the edge under
the pointer snaps to — the grid, other clips' edges, the channel's own
setting, or exactly under the pointer with `Alt`. Tested headless.

**The view turns the mouse into those two, and shows the result while the
drag lasts.** A drag edits nothing until the release. While it lasts, the
dragged clips are drawn where the release would put them, worked out by
the same functions the command uses, so what is shown is what is pushed.
The release pushes one command (`02`, *Undo*), and `Esc` before it puts
everything back with no edit at all. A preview rather than a live edit
inside a gesture: a move that overwrites its neighbours would trim and
restore them at every mouse event, and the engine at phase 8 would hear
each.

`MoveClip`, from M1, stays as it is. It exists to test the stack's gesture
merging, and nothing in the window uses it.

## Decisions settled here

**A move overwrites what it lands on, as a drop does, and a drag may cross
lanes.** The two questions the milestone left to this phase. The moved
clips are lifted first, so none trims itself or another of the selection,
and then land by `DropClips`'s rule (D-95): what they cover is trimmed,
removed or split. Every moved clip goes by the same time and the same
number of lanes, so the selection keeps its shape; the lane offset stops at
the first and last lane and the time offset at the timeline's start, for
the whole selection together. Ableton and Bitwig behave this way, and a
move that refused to land on anything would make the ordinary edit — pull a
hit onto the beat where another one is — two edits. Recorded as a decision.

**A trim stops at the neighbour.** An edge can be dragged out as far as the
clip's own sample reaches, and no further than the edge of the next clip on
its channel; in, no shorter than `MIN_CLIP_LENGTH`. A trim reveals or hides
a clip's own material; overwriting a neighbour through it is rarely meant,
and with several clips trimmed at once it has no clear answer — whose edge
wins when two selected clips on a lane both grow? The neighbour's edge is
also where a trim most often wants to stop, and stopping there makes that
exact with no snapping. Ableton overwrites instead; if that is missed, it
is one decision to reverse. Recorded as a decision.

**`MIN_CLIP_LENGTH` is 64 samples** — two of D-42's implicit 32-sample
fades end to end, so the two never overlap. A split that would leave a
part shorter is not made for that clip.

**Every verb takes the whole selection (F-51).** A move takes every
selected clip by the grabbed clip's offset. A trim moves the same edge of
every selected clip by the grabbed clip's amount, each as far as its own
limits let it. `S` splits every selected clip the playhead is strictly
inside. `Ctrl+D` copies the selection to just after itself, each copy on
its own channel, and the copies become the selection, so pressing it again
continues the run. `Delete` removes them all. Each is one command.

**How a drag snaps.** A trim snaps the edge being dragged. A move snaps the
grabbed clip's start to the grid and to clip edges, or its end to clip
edges, whichever is nearer — so a clip can be butted against a neighbour
from either side, and a clip whose length is not a whole number of grid
steps is not pulled off the grid by its end. The destination channel's
setting applies (F-18). The clips being dragged are not snap targets: their
own edges would pin every small drag to where it began.

**What a press takes.** Within `EDGE` pixels of either end of a clip — at
most a third of its width, so a narrow clip can still be moved — the press
takes that edge and the pointer shows it; elsewhere, the body. A press
selects as phase 4 made it; a drag moves or trims the selection only if the
pressed clip is selected once the press is done, so a Ctrl+press that
toggled it out drags nothing.

**The snap chip and the header's indicator become menus.** Off, the six
divisions and a *Triplet* check. The chip sets the project's snap; the
header sets its channel's override, with *Follow project* to clear it.
Choosing a division while snapping is off turns it on, and *Off* keeps the
division, so turning snapping back on returns to it. Each choice is one
command.

## Steps

1. **The edits, in `core`.** `MoveClips`, `TrimClips`, `SplitClips`,
   `DuplicateClips` and `RemoveClips`; `DropClips`'s settling of overlaps
   taken out into a function the move shares; `MIN_CLIP_LENGTH`. The two
   decisions go in `01`, and `03`'s *Rules* say what a move and a trim do.
   *Test (headless):* a move within a lane, across lanes and onto a
   neighbour, the selection kept in shape at the first lane and at 0; a
   trim from either end stopping at its sample's bounds, its neighbour and
   the minimum, and a left trim still playing the same samples; a split
   whose parts, read from a decoded sample end to end, are the original's;
   duplicate after the span and onto what is there; every one undone back
   to an equal project; `validate()` clean after each.

2. **Where a drag lands, Qt-free.** The part a press takes; the snapped
   offset of a move and the snapped edge of a trim, by the destination
   channel's setting, with `Alt`, and with the dragged clips left out of
   the targets.
   *Test (headless):* the edge zones on a wide and a narrow clip; a move
   snapping its start to the grid, its end to a neighbour's start, and
   whichever is nearer; an override and a disabled override; `Alt`; a small
   drag not snapping back to where it began.

3. **Dragging in the lanes.** A body drag moves the selection and an edge
   drag trims it, drawn where the release will put them; one command on
   release; `Esc` cancels; the pointer shows an edge.
   *Test:* a drag across two lanes moves three selected clips as one
   command, and one Undo puts them back; a drag onto a neighbour trims it;
   an edge drag stops at its neighbour; the preview during the drag is
   where the release lands; `Esc` mid-drag leaves the project unchanged
   and the stack empty; a drag that snaps back to where it began pushes
   nothing.

4. **The keys.** `S`, `Ctrl+D` and `Delete`, and Edit's three actions
   enabled exactly when clips are selected, their tooltips no longer naming
   M3.
   *Test:* each through the window's action; `S` with the playhead outside
   every selected clip does nothing; the actions disabled with channels or
   nothing selected; the rename field keeps `S` and `Delete`; no sample's
   bytes change through a session of every edit (F-14).

5. **Choosing the snap.** The chip and the header's indicator as menus.
   *Test:* every division, triplet and off, from the chip, each one
   command; the header sets and clears its override and shows which is in
   force; the grid and a drop follow the change.

6. **Written down, and looked at.** `04`'s *Timeline* says what a press
   takes, how a drag snaps, `Esc` during a drag, and the two menus; the
   keyboard table's `Ctrl+D` says where the copies go. A grab of a drag in
   progress across lanes.

## Files

```
docs/01-requirements.md                     amended — two decisions
docs/03-data-model.md                       amended — Rules: move, trim
docs/04-ui-spec.md                          amended — editing, snap menus
docs/doc-system.md                          amended — high-water mark
src/immersive/core/model.py                 amended — MIN_CLIP_LENGTH
src/immersive/core/edits.py                 amended — five commands
src/immersive/ui/timeline/dragging.py       new — Qt-free
src/immersive/ui/timeline/clips.py          amended — drawn where a drag goes
src/immersive/ui/timeline/view.py           amended — drags, Esc, cursor
src/immersive/ui/timeline/snap_menu.py      new — the division menu
src/immersive/ui/timeline/headers.py        amended — the indicator's menu
src/immersive/ui/main_window.py             amended — the chip, the keys
tests/test_edits.py                         amended — headless
tests/test_dragging.py                      new — headless
tests/test_editing.py                       new — gui
tests/test_layering.py                      amended — dragging.py is headless
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The preview and the command disagreeing | a clip shown landing in one place and landing in another | the preview is worked out by the command's own functions, and a test compares the items during the drag with the project after the release |
| A move's lift and land in the wrong order | a moved clip trimming itself, or one of the selection trimming another | the land is worked out against the channels with every moved clip already lifted; a test moves two adjacent selected clips by less than their length |
| `Alt`+drag taken by the window manager | on some Linux desktops `Alt`+drag moves the window, and the timeline never sees it | outside the application; noted in `04` if it turns up on the native test |
| A preview left behind | a clip drawn where it is not | `_lay_out` draws from the project unless a drag is in progress, and the release and `Esc` both end the drag before laying out |
| Repeated snap targets per mouse move | a slow drag over five hundred clips | the targets are gathered once when the drag begins |
| A single-letter shortcut firing in a text field | typing `s` in a channel's name splits clips | a line edit claims printable keys before any shortcut sees them; tested as phase 4 tested `Ctrl+A` |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| a move not lifting the moved clips first | a selected clip trimmed by its moved neighbour |
| the lanes not clamped together | a selection losing its shape at the first lane |
| a left trim moving the start without the offset | the clip plays other samples |
| a trim passing its neighbour | an overlap, refused by validation |
| a trim not stopping at the minimum | a clip of a few samples, or none |
| a split's tail playing from its sample's start | caught by reading the samples |
| a split's tail keeping the head's id | two clips with one id |
| duplicate placing the copies on the originals | the copies overwrite what they copied |
| each clip snapped separately | a selection pulled out of shape by the grid |
| the dragged clips among the snap targets | a small drag snapping back to its start |
| the source channel's snap used for a move to another | F-18 broken across lanes |
| a move's end not snapping | a clip cannot be butted from its left |
| the drag pushing on every mouse move | fifty Undos for one drag |
| `Esc` not cancelling | a drag that cannot be taken back without an edit |
| the chip setting the project's snap outside the stack | a snap change Undo cannot reach |
| Split enabled for channels | an action that does nothing |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Cut, copy, paste; `Ctrl`+drag to copy | phase 6 |
| Clip gain and fades, and their handles | phase 7 |
| `Shift`+drag bringing automation along (D-7) | M6. Until then `Shift`+drag is a drag |
| Scrolling while a drag is held past the view's edge | not planned; zoom out to reach. Raised if it is missed |
| A drag below the last lane making a new channel | not planned; a drop from the pool does |

## Outcome

Six steps in the planned order, all nine acceptance boxes ticked. Sixty
mutations: fifteen of the sixteen named in advance and forty-five found on
the way, all killed. 1717 tests.

### What the plan got right

**Deciding the two open questions before any code.** Every test of a move
and a trim was written against D-97 and D-98, and nothing had to be
reworked when the view arrived.

**A preview rather than a live edit.** The view builds the release's own
command at every movement. The preview and the push cannot disagree, and
`Esc` needed no undo.

**The rules in `core`, the pointer in a Qt-free module.** 22 tests of
snapping and edge zones run without a window, and the window's tests only
check that a drag reaches them.

### What the plan did not see

**That `Fade` is mutable.** A duplicate made with `replace` would have
shared its fades with the original, so editing one clip's fade would have
edited both. Each copy gets fades of its own, and a mutation holds it.

**That making the snap a button moves the window's first focus.** The
chip became the first focusable widget and opened with the accent ring.
Only the grab showed it.

**Two weak tests and one redundant line.** A Ctrl-toggled clip's drag was
tested with nothing else selected, so the mutation could not move anything
either way. A lane's colour during a drag was not tested. Clearing the
release's select-one-clip flag at drag start was a second guard: the
release already checks for a drag first. That line went.

**One named mutation had no line to mutate.** *Each clip snapped
separately*: the view works out one offset from the grabbed clip and the
command applies it to all, so there is no per-clip snapping to break. It
was not run.

### Deviations

| Planned | Actual |
|---|---|
| `test_edits.py`, `test_dragging.py`, `test_editing.py`, `test_layering.py` | and `test_timeline.py`, whose readout test read only labels and the chip is a button now |
| The chip's look not considered | a button with a drop-down arrow, out of the focus chain |
| Sixteen mutations | sixty |

### What phase 6 needs to know

`DuplicateClips` already copies clips with fresh ids and fades of their
own, and lands them as a drop does. Paste is the same landing at the
playhead on the focused channel (F-50), so `_settle` in `edits.py` is the
function to reuse. `view.focused()` is the channel last clicked.
`view.dragging()` says whether a drag is under way. A `Ctrl`+press toggles
a clip, so a `Ctrl`+drag to copy would have to begin from a press that
toggled nothing out; today it drags nothing.
