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
| [2 — Channels](phase_2_channels.md) | not started |
| [3 — Clips on the lanes](phase_3_clips_on_the_lanes.md) | not started |
| [4 — Selection](phase_4_selection.md) | not started |
| [5 — Editing clips, and snapping](phase_5_editing_and_snapping.md) | not started |
| [6 — Cut, copy and paste](phase_6_cut_copy_paste.md) | not started |
| [7 — The parameters pane, clip gain and fades](phase_7_parameters_pane.md) | not started |
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
- **What does the clipboard hold, and how far does it reach?** A clip names
  its sample by id (D-58). Pasting into another project would name a sample
  that project does not have. Refuse the paste, carry the sample along with
  the clips, or keep the clipboard to one project. Phase 6.
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
