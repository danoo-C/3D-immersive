# M3 — Timeline

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Specification:
*Timeline*, *Selection*, *Keyboard*, *Parameters pane* and *Master meter* in
[04-ui-spec.md](../04-ui-spec.md); *Time*, `Channel`, `Clip` and *Rules* in
[03-data-model.md](../03-data-model.md); *Scheduler*, *Parameter smoothing*,
*The master bus* and *Realtime safety checklist* in
[05-audio-engine.md](../05-audio-engine.md); *Threading* in
[02-architecture.md](../02-architecture.md) · Workflow:
[09-workflow.md](../09-workflow.md)

| Phase | Status |
|---|---|
| [1 — The time axis, the ruler and the grid](phase_1_time_axis_and_ruler.md) | ✅ |
| [2 — Channels](phase_2_channels.md) | ✅ |
| [3 — Clips on the lanes](phase_3_clips_on_the_lanes.md) | ✅ |
| [4 — Selection](phase_4_selection.md) | ✅ |
| [5 — Editing clips, and snapping](phase_5_editing_and_snapping.md) | ✅ |
| [6 — Cut, copy and paste](phase_6_cut_copy_paste.md) | ✅ |
| [7 — The parameters pane, clip gain and fades](phase_7_parameters_pane.md) | in progress |
| [8 — The engine, flat](phase_8_flat_engine.md) | not started |
| [9 — Transport](phase_9_transport.md) | not started |
| [10 — The master meter, and the arrangement heard](phase_10_meter_and_listening.md) | not started |

The order is dependency order. Channels need a view and a time axis to be
drawn against; clips need a lane to land on; the edit verbs act on a
selection, so selection comes before them rather than after; paste needs
both. The pane edits what selection picks. The engine is built headless,
against a stand-in stream, and can be built in any order relative to the UI
phases; it sits eighth so that it is written against the finished model
rather than one still growing fields. Transport joins the engine to the
window, and the meter is last because it can only be judged with real sound
coming out — the one thing in this milestone that cannot be finished on WSL.

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> you can build an arrangement and hear it play back flat.

The roadmap's reason, which is what the milestone is really for: it
validates the realtime plumbing — command ring, snapshot swap, xrun counting
— before any HRTF complexity is layered on top.

## Starting with M2's last box open

M2 is built but not complete. Its phase 7 waits on a person listening on
native Windows or Linux ([phase 7](../m2_media/phase_7_audition.md)), and
M2 stays *in progress* in the roadmap until then. Nothing in M3 rests on
that box: the engine is new code with its own tests. M3's last phase needs
the same machine, so both listening tests can happen in one sitting.

## Scope amended before the milestone started

Five changes to the roadmap's list, made while M3 is *not started*, which is
when [09-workflow.md](../09-workflow.md) says scope may change freely.

**Per-clip gain and fades (F-15) are added.** No milestone had them. Clips
are M3's, the scheduler that applies gain and fades is M3's, and
[04](../04-ui-spec.md)'s vocabulary table already gives M3 the `fade handle`
group — for a handle nothing was going to draw.

**The parameters pane is added, for the selections M3 introduces.** Clip
gain and fade shape have no other editor in `04`, and the pane "follows the
selection" (`04`, *Selection*), which is M3's to build. M5's roadmap entry
adds position fields to a pane the roadmap never builds. Fields that belong
to later milestones are drawn disabled, with the milestone that brings them,
as every unbuilt action already is. The channel header's gain field
(phase 2) and the pane (phase 7) are the first widgets to take typed input,
so the groups `04` lists under M8 for input widgets come here instead — as
`04` itself says they should, to whichever milestone first draws one.

**Implicit edge fades (D-42) move here from M4.** The scheduler is built at
M3, and split and trim — also M3 — produce mid-waveform edges by
definition. An M3 that played them without the fade would click at every
split, and the milestone's acceptance is listening to that playback.

**The zero-allocation test on `process()` starts here.** The flat engine is
the first code on the audio thread that runs for longer than one sample.
Writing it without the test that enforces
[05](../05-audio-engine.md)'s checklist would leave M4 to find and rip out
whatever allocates. M4's bullet stays: it holds the spatial path to the same
test.

**The `TimeAxis` is made explicit.** The risk register's mitigation for the
curve editor and the timeline drifting apart is one shared object that owns
scroll and zoom, with both widgets observing it. The timeline is the first
observer and M6's curve editor the second, so the object is built in phase 1.
A timeline that owned its own scroll and zoom would be the drift, built in
advance.

## What this milestone does not deliver

| Not here | Where |
|---|---|
| Spatialisation, distance attenuation, the bypass path and its pan law | M4. M3 plays everything flat: a mono clip to both ears, a stereo clip as it is. The bypass *flag* is M3's; what it does to the sound is M4's |
| Master gain and the limiter | M4, with the master bus |
| `sys.setswitchinterval` (D-39) and the thirty-two-source benchmark | M4, which measures both under load |
| Shift+drag bringing automation along with a clip (D-7, F-31) | M6, with the automation |
| Position and pan fields in the parameters pane | M5 and M4; drawn disabled here |
| The keyframe editor observing the time axis | M6. M3 builds the axis it will observe |
| Custom channel colours beyond the palette | M8, the first milestone with dialogs. M3 recolours from the eight |
| Remembered splitters, ruler unit and window geometry | M8, after beta |
| The relink dialog | M8, before beta (D-84) |

## Questions the plans must settle

Found while writing the phase docs, and left open on purpose — each is its
phase's first decision.

- **Where does the `TimeAxis` live, and how do painted items take a theme
  change?** It owns no widget and M6 shares it, which argues for a Qt-free
  object; scroll and zoom are view state, which argues for `ui/timeline/`.
  M9's repaint walk reaches only `QWidget`s, so anything in a
  `QGraphicsScene` has to be rethemed by its view or read its colours when it
  paints ([M9's roadmap entry](../06-roadmap.md) carries the warning).
  Phase 1.
- **What does moving a clip onto a neighbour do, and can a drag change
  channel?** `03` says a *drop* onto an occupied span trims the clip
  underneath, and a modifier refuses the drop instead. It says nothing about
  a *move*. `04` says "drag body to move" without saying whether a vertical
  drag crosses lanes, and no command moves a clip between channels today.
  Phase 5.
- ~~**What does the clipboard hold, and how far does it reach?**~~ Copies
  of the clips, and no further than the open project: New and Open empty it
  (D-99, phase 6).
- **What goes in an engine snapshot, and what is a parameter change?** `02`
  sends structural changes as a whole new snapshot and parameter changes
  through a command ring. Which side gain, mute and solo fall on, and how a
  swap is made atomic in Python without a lock, are the phase's design.
  Phase 8.
- **Audition and the transport — one stream or two?** M2's audition opens
  its own stream. Two streams on one device are not possible on every
  backend, and one stream means audition goes through the engine. Either
  way, a double-click during playback has to do something defined.
  Phase 9.
- **Which drag in the ruler moves the playhead, and which draws the loop
  region?** Both are phase 9's, and "drag in the ruler" cannot mean both.
  Two common answers: grab the playhead's head to move it and drag anywhere
  else for a loop (REAPER), or give each its own strip (Logic). Whether the
  dragged playhead snaps goes with it. Added before phase 9 started.
  Phase 9.

## Notes

Appended as phases complete.

**Phase 1.** The timeline has a view, a ruler and a grid on one shared time
axis, and the axis is a Qt-free object the window holds — not the
timeline's, because M6's curve editor observes it too (D-94). Its scroll
offset is whole pixels, so the ruler and the lanes cannot come apart. The
grid is placed as `core.time` places bars and snap targets, and thins by a
rule judged on everything drawn together, which the plan had judged series
by series. The colours were already named: `04`'s worked example of a theme
file had a `timeline` group, and the lanes draw from it. Twenty-six
mutations, all killed.

**Phase 2.** Channels: a header of real controls beside each lane — chip,
name, the numeric field for gain, M, S and bypass, and the snap indicator —
each edit one command, and a column placed against the lanes' own scroll
so a header is always level with its lane. Adding, removing, renaming,
recolouring and dragging to reorder, all undoable. The numeric field is
built once here, for the pane and the playhead readout to reuse, and the
input group with it. Headers are rebuilt only when the list of channels
changes, and compared by identity, because a reopened file's channels are
equal to the ones on screen and not the same. Twenty-three mutations, all
killed.

**Phase 3.** Clips: dragged from the pool onto a lane, snapped to the grid
and to any clip's edges, several end to end, and below the last lane into a
new channel — each drop one Undo. A drop inside a longer clip splits it
(D-95). A clip is its channel's colour with its own part of its sample
drawn in it, grey and saying so when the sample is missing. M2's waveform
drawing learned ranges, and a seam between strips was caught by a test
before anything was drawn. Five hundred clips were measured: scrolling is
inside a frame, and two causes of a slow cold repaint were found and fixed,
one of them a lookup every paint in the application was paying. Twenty-two
mutations, all killed.

**Phase 4.** Selection: clips by clicking, Shift and Ctrl, and a rubber band
across lanes; channels by their headers; samples by their rows in the pool
— one kind at a time, and each widget reading one selection the document
owns and prunes after every change (D-96). `Ctrl+A` takes the focused
channel and then everything; `Esc` clears while the transport is stopped,
which until phase 9 it always is; `B` bypasses the selected channels as one
edit. A selected clip wears a border and a selected header a bar, so
neither is marked by colour alone. Twenty-seven mutations, all killed; two
survived at first, both ranges tested in a way that could only grow.

**Phase 5.** Editing: a selection moved by its body, across lanes too,
overwriting what it lands on (D-97); trimmed from either edge, stopping at
the neighbour and at its sample's ends (D-98); split at the playhead,
duplicated after itself, and deleted, each one Undo. A drag edits nothing
until the release and is drawn meanwhile by the command the release will
push, so `Esc` has nothing to undo. Every edge snaps to the grid and to
other clips' edges by the channel it lands in, or not at all with `Alt`.
The snap chip and each header's indicator choose the setting from a menu.
No sample file is written. Sixty mutations, all killed.

**Phase 6.** Cut, copy and paste: `Ctrl+C` copies the selected clips, which
is not an edit; `Ctrl+X` is Copy then Delete as one Undo; `Ctrl+V` lands
them at the playhead on the focused channel, keeping their spacing in time
and across lanes, overwriting what they cover, and selected. The clipboard
holds copies and belongs to the open project, emptied by New and Open, and
Paste is disabled while a copied clip's sample is out of the pool (D-99).
Lanes a paste needs past the last become channels in the same edit
(D-100). A numeric field at rest no longer claims `Ctrl+C`. Forty-five
mutations, all killed but one, which is equivalent and pinned by a test.
