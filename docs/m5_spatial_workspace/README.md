# M5 — Spatial workspace

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Specification: *The
workspace is tabbed* and *Workspace (centre)* in
[04-ui-spec.md](../04-ui-spec.md); `Position` and `Placement` in
[03-data-model.md](../03-data-model.md); where every spatial setting is set,
D-135 · Workflow: [09-workflow.md](../09-workflow.md)

| Phase | Status |
|---|---|
| [1 — The ortho views, drawn](phase_1_ortho_views.md) | ✅ |
| [2 — Dragging, heard](phase_2_dragging.md) | ✅ |
| [3 — What an icon says, and the bypass strip](phase_3_icons_and_bypass.md) | ✅ |
| [4 — The 3D view](phase_4_view3d.md) | ✅ |
| [5 — Measured with the views playing](phase_5_measured.md) | not started |
| [6 — Heard](phase_6_heard.md) | not started |

The order is dependency order. The top and front views are drawn first,
with the head, the rings and every channel where it is, and a click selects
a channel. Then dragging: the point of the milestone, heard while it moves.
Then what an icon tells at a glance, and where bypassed channels go. Then
the read-only 3D view, which draws what the ortho views already know. The
views repaint during playback, which is what M4 phases 10 to 12 made safe,
so the fifth phase measures it with the views as the load. Hearing is last
because only a person can do it.

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> you can drag a sound around the head while it plays and hear it move.

## Starting with M4's last box open

M4 is built. Its phase 13 waits only on the listening machine, and the user
has already heard their own stems placed and approved them (phase 13's
Notes). Nothing here rests on that box: M5 draws and moves the positions M4
plays, through the same fields and commands.

## Scope amended before the milestone started

**Motion trails and keyframe diamonds move to M6.** A trail is drawn from
a channel's `pos.*` curves, and nothing can make one until M6's keyframe
editor. Its "where the source is right now" dot would move while the sound
stayed where it was, because the engine plays curves only from M6. So M5
would draw something no project has, and draw it wrong when one did. M6's
"Done when" already asks to "watch the trail, the curve and the sound
agree", and it builds all three together. The roadmap's M5 line is struck
through and says where it went.

**04's workspace section said "three panes side by side"**, after D-49 had
made them two tabs. It is corrected to the tabs, as its own opening section
already says.

## Questions the plans must settle

Found while writing the phase docs, and left open on purpose. Each is its
phase's first decision.

- **How the views are scaled and moved.** How many metres the view shows at
  first, how far zoom goes, and whether the top and front views share their
  X scale and pan, since they show the same X. (Phase 1.)
- **The views' colours.** The head, the rings and the ear-level line need
  theme tokens, in a group of their own (D-92). (Phase 1.)
- **How a drag is heard before it is an edit.** One gesture is one undo
  step (02, *Undo*), and the timeline's drags edit nothing until the
  release. But a source dragged during playback must be heard moving. The
  engine's command ring can carry positions no edit has made yet. (Phase 2.)
- **A pair on the canvas.** Which side leads when a linked pair is dragged,
  whether the pivot is drawn and dragged, and what a switch between Free and
  Linked keeps. M4 left the left side always leading. (Phase 2.)
- **What the views cost to repaint during playback.** A full repaint of the
  window with 32 channels took 55 ms at M4 phase 10, and the views will
  repaint at the frame rate while sources move. (Phase 5.)

## What this milestone does not deliver

| Not here | Where |
|---|---|
| Motion trails, keyframe diamonds, the "now" dot | M6, with the curves they are drawn from |
| Positions that move by themselves | M6: automation |
| A GL scene, or a camera for the 3D view | not in v1 (04: `QPainter`, fixed camera) |
| Loading a SOFA of one's own | M8 |

## Notes

Appended as phases complete.

**Phase 1.** The top and front views replace their placeholders: the head,
rings a metre apart in the top view, lines of height in the front, and
every channel's point or pair where its position puts it. A click selects,
and the selected are ringed and drawn on top. They share one scale, zoomed
by scroll and panned by middle-drag (D-143), and keys 1 to 3 focus them.

**Phase 2.** A source is dragged in either view and heard moving before the
release: the drag is held apart from the model and sent to the engine at
each movement, and the release is one edit (D-144). A pair is dragged by
either side, the side grabbed leading (D-145). Esc drops a drag in the
window too, where it is also Stop, and an edit made mid-drag drops it.

**Phase 3.** An icon's radius says how near it is and its opacity how loud,
and a channel not heard, muted or silenced by a solo, is at a quarter; a
soloed one glows (D-146). Bypassed channels are chips in a strip under the
top view, wrapping into rows, hidden when there are none (D-147).

**Phase 4.** The 3D tab shows the scene from a fixed true isometric camera
behind the listener and to their left (D-148): the ground at ear level,
stepped to hold every source, a drop line for each source's height, and
the icons drawn farthest first by the ortho views' own rules. It takes no
input.
