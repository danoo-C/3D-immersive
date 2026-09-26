# Plan — M3 · Phase 6 — Cut, copy and paste

**Written:** 2026-09-26 · **Status:** ✅ complete

## Approach

Two layers, as in phase 5. **What a paste does belongs to `core`**. A
Qt-free `Clipboard` holds what was copied. `PasteClips` works out at
construction everything it will change, as the other clip edits do, so
`do()` and `undo()` only apply one set of lists and placings or the other.
Where a paste lands, what it overwrites, the channels it makes and the ids
it mints are all tested without a window.

**The window gives it keys.** Edit › Cut, Copy and Paste work as Split,
Duplicate and Delete already do. Each reads the selection, the focused
channel and the playhead, and pushes at most one command. Copy pushes
nothing, because it changes nothing in the project.

The one real alternative was the system clipboard, `QClipboard`, holding
clips as a MIME payload the way the pool's drag already does. It was
rejected. Nothing outside the application reads clips (the phase's *Out*),
and a payload written there outlives the project it names, which is exactly
what D-99 refuses.

## Decisions settled here

**The clipboard belongs to the open project (D-99).** This is the question
the milestone left to this phase. The clipboard holds copies of the clips,
taken when Copy or Cut is pressed, each with its lane counted from the
topmost copied clip and its start from the earliest. The `Document` owns it,
beside the selection, and empties it when the project is replaced. Paste is
disabled, and says why, while any copied clip's sample is no longer in the
pool, which only an Undo of its import can do. Refusing the whole paste
beats leaving some of it out, because a paste missing part of what was
copied loses material without a word.

**Where a paste lands (D-100).** At the playhead, on the focused channel,
which `Ctrl+A` also reads. With no channel focused, it lands on the lane the
topmost copied clip came from, and failing that on the first lane. Every
clip keeps its distance from the earliest in time and from the topmost in
lanes, gaps included, so a phrase copied from lanes 1 and 3 pastes onto two
lanes one apart. It overwrites what it lands on, as a drop does (D-95).
Lanes it needs past the last become new channels, named and coloured in
turn, inside the same edit. The pasted clips become the selection.

The acceptance's "consecutive channels from the selected one down" reads as
this: clips copied from adjacent channels paste onto adjacent channels, and
the phase's *Scope* keeps the spacing across channels, which settles any
gap.

**The playhead does not move after a paste.** Pressing Paste twice pastes
twice at the same place, and the second overwrites the first. `Ctrl+D` is
the key for carrying a run on, and a paste that moved the transport would
be the first edit to do so.

**Cut is Copy and then Delete, as one command.** The clipboard is filled
first, then `RemoveClips` is pushed. Undo puts the clips back and leaves
the clipboard alone, as in every editor.

**Copied clips take nothing with them.** They carry gain and fades,
copied, since `Fade` is mutable (phase 5's lesson). The pasted clip gets a
fresh id. Automation stays behind (the phase's *Out*).

## Steps

1. **The clipboard and the paste, in `core`.** `core/clipboard.py` with
   `Clipboard`: `hold(project, clips)`, `clear()`, whether it holds
   anything, which lane a paste goes to, and whether it can be pasted into
   the project as it stands. The `Document` owns one and empties it in
   `_replace`. `PasteClips` goes in `edits.py`: new channels past the last,
   fresh ids and fades of their own, landing through `_settle`, and the
   copies it made. The two decisions go in `01`, `03`'s *Rules* say what a
   paste does, and `02`'s module map gets `clipboard.py`.
   *Test (headless):* the clipboard holds copies, so moving or trimming an
   original afterwards does not change what pastes; the spacing is kept in
   time and in lanes, a gap lane included; the ids are fresh and distinct
   from each other; the fades are the pasted clips' own; the originals are
   untouched; a paste over clips trims, removes and splits them by D-95; a
   paste past the last lane makes channels named and coloured in turn, and
   one Undo takes them away again; round trip and run twice (added to
   `EDITS`); a paste whose sample has left the pool cannot be made; the
   lane is the focused channel, else the topmost source lane, else the
   first; the clipboard is emptied by New and Open and survives edits and
   Undo; the random runs gain a paste.

2. **Cut, copy and paste in the window.** Edit › Cu&t (`Ctrl+X`), Copy
   (`Ctrl+C`) and Paste (`Ctrl+V`). Cut and Copy are enabled exactly while
   clips are selected, and Paste exactly while the clipboard can be pasted,
   whatever is selected. The tooltips no longer name M3 and say what is
   missing when disabled. A resting numeric field claims no shortcut (see
   *Risks*).
   *Test (gui):* copy and paste at the playhead on the focused channel, the
   originals untouched and the copies selected; Cut is one command, and a
   paste afterwards brings the clips back; clips from two lanes paste onto
   two lanes from the focused one down, and past the last one make a
   channel; a paste over a clip trims it; one Undo takes back a whole
   paste; Copy leaves the project clean and the stack as it was; Paste is
   disabled after Undo removes the sample, and after New; the rename field
   and the pool's filter keep `Ctrl+X`, `Ctrl+C` and `Ctrl+V`, while a
   resting gain field keeps none of them.

3. **Written down, and looked at.** `04`'s *Keyboard* table says where a
   paste lands; *Timeline* describes cut, copy and paste; *Selection* says
   the focused channel is also where a paste goes. The M3 README's clipboard
   question is struck through, with its answer. A grab of a phrase pasted
   across two lanes onto a new channel.

## Files

```
docs/01-requirements.md                     amended — two decisions
docs/02-architecture.md                     amended — clipboard.py
docs/03-data-model.md                       amended — Rules: a paste
docs/04-ui-spec.md                          amended — cut, copy, paste
docs/doc-system.md                          amended — high-water mark
docs/m3_timeline/README.md                  amended — the question struck
src/immersive/core/clipboard.py             new — Qt-free
src/immersive/core/document.py              amended — owns a clipboard
src/immersive/core/edits.py                 amended — PasteClips
src/immersive/ui/main_window.py             amended — Cut, Copy, Paste
src/immersive/ui/widgets/numeric.py         amended — at rest, no shortcuts
tests/test_clipboard.py                     new — headless
tests/test_edits.py                         amended — PasteClips
tests/test_pasting.py                       new — gui
tests/test_numeric.py                       amended — keys at rest
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A resting numeric field swallowing `Ctrl+C` | copying the gain's text instead of the clips. A read-only `QLineEdit` still claims Copy (measured: it accepts `Ctrl+C` and passes `Ctrl+V` and `Ctrl+X`), and the field keeps focus after Enter commits a value | a field at rest claims no shortcut, since it is not being typed into. Tested at rest and while typing |
| Several new channels made at once all given one name and colour | `new_channel` looks at the project's last channel, and none of the new ones is in the project yet | each is made against the project as it would stand with the earlier ones added, so the turn and the name carry on. Tested with three |
| An id minted twice | a pasted clip and a split tail given the same id in one paste | one `taken` set for the whole command: pasted ids, tail ids and the new channels' ids |
| Paste state going stale | Paste enabled over a sample an Undo just removed | the action is worked out again after every change the document reports, as well as after Copy and Cut |
| `Ctrl+X`/`C`/`V` taken by a widget that should not have them | the pool's tree copying its row's text | the window's actions are window shortcuts, so they fire before an item view sees the key. Tested from the tree |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| the clipboard holding the clips, not copies | a paste lands where the original has since moved |
| a pasted clip keeping its copied id | two clips with one id, refused by validation |
| the fades shared with what was copied | editing a pasted fade edits the original's |
| starts not counted from the earliest | the paste lands late by the first clip's start |
| lanes not counted from the topmost | the paste skips lanes |
| a gap lane closed up | spacing across channels lost |
| a paste not settling what it lands on | an overlap, refused by validation |
| no channel made past the last | a paste past the end fails or drops clips |
| every new channel made against the project as it is | two new channels with one name and colour |
| Undo leaving the new channels | empty channels left behind after an Undo |
| the clipboard kept when the project is replaced | a paste naming a sample the new project does not hold |
| Paste enabled with a sample gone | a clip naming nothing |
| the focused channel ignored | every paste lands on the copied lanes |
| no fallback to the source lane | a rubber-banded phrase pastes on the first lane |
| Copy pushing a command | copying marks the project unsaved |
| Cut as two commands | two Undos for one Cut |
| Paste disabled with nothing selected | no paste after `Esc` |
| the pasted clips not selected | a paste cannot be moved at once |
| a resting numeric field claiming shortcuts | `Ctrl+C` copies text |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| `Ctrl`+drag to copy | not planned. A `Ctrl`+press toggles the selection (phase 4), so a copying drag needs a rule of its own. Raised if missed |
| Pasting into another project, or from another application | not planned (D-99) |
| Copying channels, or samples in the pool | not planned. F-50 is about clips |
| Automation copied along with clips | M6, if at all |
| Scrolling to show what was pasted | not planned. The playhead is where the person was looking |

## Outcome

Three steps in the planned order, and all seven acceptance boxes are
ticked. Forty-five mutations: all nineteen named in advance, and
twenty-six found on the way. Forty-four are killed. One is equivalent and
pinned by a test. 1776 tests.

### What the plan got right

**Settling the clipboard before any code.** Every test was written
against D-99 and D-100, and nothing was reworked when the window arrived.

**The rules in `core`.** Where a paste lands, what it overwrites, the
channels it makes and the ids it mints are 28 headless tests. The
window's 19 only check that the actions reach them with the right
selection, channel and playhead.

**Measuring the numeric field while planning.** The risk table's first
row was found by trying it, not by guessing. A read-only line edit claims
`Ctrl+C` and passes `Ctrl+V` and `Ctrl+X`. The fix and its test were
scoped before the window step began.

### What the plan did not see

**That the id test could not fail.** A test counting distinct ids after a
paste passes whatever the code does, because 32-bit random ids do not
collide in a test run. Two mutations to the shared `taken` set would have
survived it. A random source that repeats itself makes a collision certain
if the code allows one.

**Two missing tests in `core`.** Clips given out of lane order found that
every test had passed them topmost first. A cleared clipboard still aimed
at its source was invisible until a test asked where an empty paste would
go. Both survived the first run and are killed now.

**That `setShortcut` takes only a standard key's first binding.** The
comment beside the three actions said `StandardKey.Cut` would add
`Shift+Del`. It would not, so swapping the spelled-out key for the standard
one is an equivalent mutation. The comment is corrected, and a test pins
why.

### Deviations

| Planned | Actual |
|---|---|
| `test_numeric.py` amended for the keys at rest | and for the keys while typing, which the first test alone could not tell from never claiming |
| Nineteen mutations | forty-five |

### What phase 7 needs to know

`Document.clipboard` is the second thing the document owns beside the
project, after the selection. It is not observed: the window works Paste
out again on every document change and after Copy. A pane that shows the
selection can read `selection.clips()` as before. Pasted clips are
selected, so the pane will follow a paste without anything further.
`PasteClips.copies` is the clips a paste made, in lane order and then time
order. A numeric field at rest claims no shortcut, so the pane's fields
will not swallow `Ctrl+C` either.
