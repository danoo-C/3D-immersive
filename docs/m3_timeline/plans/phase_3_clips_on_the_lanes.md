# Plan — M3 · Phase 3 — Clips on the lanes

**Written:** 2026-09-26 · **Status:** in progress

## Approach

Three layers again. **Where clips go is `core`'s**: a command that places
clips on a channel and settles every overlap the placement makes, tested
with no window. **How a clip looks is an item's**: a `QGraphicsItem` per
clip, painted from the project and the session's peaks, with nothing about
the arrangement decided in it. **What a drop means is the view's**: the
lane under the pointer, the sample under it snapped, the samples in the
drag. It turns all of that into one command.

**The drawing is M2's, taught to draw part of a sample.** A clip trimmed to
its middle shows only its middle, so the waveform module gains an envelope
over a range of frames, and `paint_peaks` becomes a caller of it rather than
the only thing that knows how. The clip draws its body, its name and that
range. The pool's thumbnail draws the whole sample, as it did.

**Items are cached by Qt, per device pixel.** `DeviceCoordinateCache` keeps
what a clip last painted and repaints it when its geometry changes — on a
zoom — or when it is told to — its peaks arrived, its channel was recoloured,
the theme changed. Scrolling reuses what was painted. That is *cached
waveform pixmaps per clip* from `04`'s *Timeline*, without a second cache of
our own to keep honest. Whether Qt caches only the exposed part of a clip
wider than the view is checked in step 2 before anything relies on it.

**Items are kept by identity.** After each change the view compares the
clips it shows with the project's, the same way the headers compare
channels. Items that still belong to their clips are updated, new clips get
new items, and gone clips lose theirs. A zoom lays out every item again; a
scroll lays out none.

## Decisions settled here

**Several samples dropped together go end to end on one channel**, from the
drop point, in the order the pool lists them. That is the order a person
selected them in and the order they read. Dropped below the last lane, they
make one new channel holding all of them. `04` says "a channel holding it";
several is the same gesture, and one channel keeps them together.

**A drop over existing clips trims them (`03`, *Rules*), and a drop wholly
inside a longer clip splits it around the drop.** `03` says "trims" and does
not say what happens when the existing clip reaches past both ends of the
drop. Trimming one side would delete material the person never covered, and
refusing the drop would make a drop into the middle of a long backing track
impossible. Splitting keeps both outer parts where they were. This is a
judgement between real alternatives, so it is recorded as a decision in `01`
and the rule is amended in `03`.

**Shift refuses a drop that would overlap**, the modifier `03` asks for.
`Alt` is taken by snapping, and Ctrl means *copy* to most platforms'
drag-and-drop. While Shift is held over an occupied span, the drag shows the
platform's no-drop cursor rather than accepting and then doing nothing.

**A drop snaps to the grid and to every clip's edges, on any channel**
(F-17). Lining up with what is on the channel above is most of what snapping
to edges is for. It uses the target channel's snap setting (F-18), and
nothing while `Alt` is held.

**The clip's colours.** `04`'s worked example already names the `clip` group
and gives `body` the reserved value `channel`. This is the first key painted
per channel, so `theme` gains the one function that resolves it against a
channel's colour.

| Key | Default | For |
|---|---|---|
| `body` | `channel` | the clip, drawn translucent over its lane |
| `waveform` | `channel` | the envelope, drawn solid over the body |
| `text` | `text.primary` | the clip's name |
| `missing` | `text.disabled` | the body of a clip whose sample has gone |

A missing clip is grey and says *⚠ missing* in text, as the pool's rows do.
`timeline.drop` → `accent` is the outline of where a drop will land.

## Steps

1. **Placing clips, in `core`.** `DropClips(project, channel, clips)`: it
   adds the clips and settles every overlap — an existing clip covered
   entirely is removed, one overlapping either end is trimmed, and one
   reaching past both ends is split — all worked out at construction and
   undone whole. It is tested alone and inside a `Compound` with
   `AddChannel`, which is what a drop below the last lane pushes. The
   decision goes in `01` and `03`.
   *Test (headless):* every overlap case, alone and together;
   `model.validate()` clean after each; undo restoring every clip's fields
   and the list's order; redo equal to the first time; offsets moved so
   that a trimmed head still plays the samples it played before.

2. **Envelopes over a range, and clip items.** `waveform.envelope` over a
   frame range; `ClipItem` with body, name, waveform and the missing state;
   the level of detail — no waveform when narrower than a few pixels, the
   name elided and then dropped; `theme.channel_group_color`; the `clip`
   group. The view keeps items by identity and lays them out on a zoom; the
   window tells the timeline when peaks arrive.
   *Test:* an envelope of a range equals the whole envelope's columns over
   that range; a clip drawn in its lane at its start, in its channel's
   colour; a trimmed clip's waveform is its range and not its sample's
   start; missing is grey and says so; a paint counter shows a repaint
   reuses the cache and a zoom does not; recolouring the channel repaints
   its clips.

3. **Dropping.** The view accepts the pool's MIME type: the lane from y, the
   sample from x snapped, several end to end, below the last lane a new
   channel, Shift refusing an overlap, `Alt` exact, and an outline of where
   the drop will land. The drop is one command.
   *Test:* a drop at a known x lands on the snapped sample and not the raw
   one; with `Alt`, on the raw one; several end to end; below the last lane
   a new channel with all of them, undone in one step; over an existing clip
   it is trimmed; with Shift over an occupied span it is refused and nothing
   changes; a drag of something else is not accepted.

4. **Five hundred clips.** A project of five hundred clips opened, scrolled
   and zoomed; the full repaint measured and recorded against the 16 ms of a
   60 Hz frame. Anything the measurement shows is fixed here.

5. **Written down.** `04` — the drop rules, the clip's look, the groups;
   the example's test expecting only the `clip` keys still to come.

6. **Looked at.** A grab of a real arrangement: several channels, clips
   long and short, trimmed, one missing.

## Files

```
docs/01-requirements.md                     amended — a decision
docs/03-data-model.md                       amended — the split
docs/04-ui-spec.md                          amended — drops, clips, groups
docs/doc-system.md                          amended — high-water mark
src/immersive/core/edits.py                 amended — DropClips
src/immersive/ui/theme.py                   amended — per-channel colour
src/immersive/ui/widgets/waveform.py        amended — ranges
src/immersive/ui/timeline/clips.py          new — ClipItem
src/immersive/ui/timeline/view.py           amended — items, drops
src/immersive/ui/timeline/panel.py          amended — the store
src/immersive/ui/main_window.py             amended — peaks arriving
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — groups
tests/test_edits.py                         amended
tests/test_waveform.py                      amended
tests/test_clips.py                         new — gui
tests/test_theme_io.py                      amended — the example
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The device cache holding a whole long clip | an hour-long clip at a close zoom is millions of pixels wide | check in step 2 what Qt caches for an item wider than the view, before relying on it |
| The waveform drawn one line per column in Python | a full timeline of waveforms missing a 60 Hz frame | measured at step 4, and drawn with one `drawLines` call per clip if it does |
| Drag-and-drop impossible to drive in tests | a drop tested only by hand | the view's drop handling takes its facts from the event, so tests send `QDragEnterEvent`, `QDragMoveEvent` and `QDropEvent` with real `QMimeData` |
| Splitting inventing ids | a split clip's tail colliding with an id already used | mint against the project and against each other, as imports do |
| Redo after the project moved on | a placement worked out for a state that has gone | the stack only redoes onto the state it undid from, which is the state the placement was worked out for |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| a covered clip kept | two clips overlapping |
| a trimmed head keeping its offset | the head plays the start of its sample instead of its own |
| a containing clip trimmed, not split | the material after the drop deleted |
| undo leaving a trimmed clip trimmed | Undo does not put the arrangement back |
| the envelope reading the sample from its start | a trimmed clip shows the wrong waveform |
| the channel's colour ignored | every clip one colour, breaking `04`'s colour thread |
| missing shown by colour alone | *Accessibility and feel*, broken |
| the cache dropped | every scroll repaints every waveform |
| a drop not snapped | clips a sample off the grid |
| `Alt` ignored | no way to place a clip off the grid |
| several dropped on top of each other | the second drop trims the first |
| below the last lane, a channel per sample | one drop, five channels |
| Shift ignored | an overlap the person asked to refuse |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Selecting, moving and trimming clips | phases 4 and 5 |
| Fade handles, clip gain | phase 7 |
| Hearing them | phases 8 and 9 |
| Dropping files from outside the application | not planned; import them into the pool |

## Outcome

Filled in at the end.
