# M3 · Phase 9 — Transport

**Status:** ✅ complete · **Plan:**
[plans/phase_9_transport.md](plans/phase_9_transport.md)

## Goal

Play, pause, stop and return to start work from the toolbar, the Transport
menu and the keyboard (F-20). The playhead moves with the audio and the
timeline follows it. A loop region dragged in the ruler loops playback while
looping is on. The playhead readout shows the position in the ruler's unit
and takes a typed one (F-52). The xrun counter sits in the status bar, quiet
at zero. This is the phase where the window first plays an arrangement.

## Scope

**In:** the transport actions and their keys — `Space`, `Esc`, `Enter`,
`L` (`04`, *Keyboard*); the engine on the stream `--device` and `--block`
chose (D-63); the playhead position published by the engine and read by the
window at frame rate; the view following a playhead that leaves it, as the
plan decides; seeking by clicking the ruler during playback; the playhead dragged
along the ruler, stopped or playing, as the plan decides for its snapping
and for sharing the ruler with the loop drag; the loop region,
dragged in the ruler and drawn in the `loop region` group, looping exact to
the sample; the playhead readout, in bars.beats.ticks or minutes:seconds,
drag-scrubbable and typeable with phase 2's numeric field; the xrun counter
(`04`, *Accessibility and feel*); a device lost mid-playback stopping the
transport, holding the playhead and saying so (`05`, *The output stream*);
audition's place beside the transport, as the plan decides; `Esc` clearing
the selection only while stopped.

**Out:** the meter → phase 10. What a real device sounds like → phase 10.
Render ranges built on the loop region (F-53) → M7. Hearing the audio under
a dragged playhead (scrubbing) → not planned.

**Amended before the phase started (2026-09-26).** The playhead dragged
along the ruler is added to *Scope*, with an acceptance line. No document
had it; until now only a click in the ruler moved the playhead. It belongs
here rather than in an earlier phase because this phase also makes a drag
in the ruler draw the loop region, and the two gestures have to be designed
together. It also needs seeking the engine to mean anything during
playback.

## Acceptance

- [x] `Space` starts playback from the playhead and pauses where it is,
      `Esc` stops, and `Enter` returns the playhead to the start — asserted
      through a stand-in stream, on what the engine is asked to do.
- [x] During playback the drawn playhead is where the engine last said it
      was, updated at frame rate.
- [x] With a loop region dragged in the ruler and looping on, playback runs
      from its start to its end and continues from its start with no gap and
      no repeated sample — asserted on the samples the stand-in receives.
- [x] The readout shows the playhead in the ruler's unit, and a position
      typed in either unit moves it (F-52).
- [x] Clicking the ruler during playback seeks there.
- [x] Dragging the playhead along the ruler moves it with the pointer,
      stopped or playing, and never starts a loop region; drawing a loop
      region never moves the playhead.
- [x] The xrun counter is quiet at zero and drawn in `error` once there is
      one.
- [x] A device lost during playback stops the transport, leaves the playhead
      where it was, and posts one notice.
- [x] A double-click in the pool during playback does what the plan
      decides, and the Notes say why.
- [x] Every transport action and the readout are live, and no tooltip in
      the window names M3 any longer.

## Implements

F-19 (the readout's unit), F-20, F-52, D-63 — *Transport and the ARM
toggle*, *Keyboard* and *Accessibility and feel* in
[04-ui-spec.md](../04-ui-spec.md), *The output stream* in
[05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.

**One stream, the transport's (D-107).** The milestone's question. Audition
became a voice in the engine, summed into the bus over the arrangement, so
a sample double-clicked during playback is heard against it. That is what
this phase's acceptance asked the Notes to say. M2's `audio/audition.py`
became `audio/player.py`, and its tests moved with it. The stream opens on
first use and stays open, so the ring drains while stopped; before it has
ever opened, the player applies the ring itself.

**The ruler's three gestures (D-109), and the loop region the project's
(D-108).** The playhead is taken within 5 px; a drag elsewhere draws a
loop; a click seeks; all three snap by the project's setting. The region
is saved and undoable, and the switch is the transport's, off when a
project opens. Drawing a region turns it on.

**Pause holds, Stop returns (D-110).** Space pauses where it is. Esc goes
back to where playback started, and while stopped clears the selection,
keeping phase 4's rule. Enter goes to 0.

**A bug from phase 8, found by a test.** A snapshot taken up kept the
levels it was built with. So a gain sent after it was built but before it
played - a mute made before the first Play - ramped in over the first
block. Every channel now starts at its target, with the carry laid over
that.

**Enter and Esc are the transport's now, and line edits do not claim
them.** Typing a gain and pressing Enter would have sent the playhead to 0,
and Esc in a rename or during a clip drag would have stopped the transport.
A field that commits or cancels, and a drag, now claim the keys while they
have them.

**The allocation test was flaky under pytest-xdist**, one parallel run in
six: `tracemalloc` counts every thread, and the worker's messaging thread
allocated during a block. It now measures in an interpreter of its own.
Mutations its failures had seemed to catch were run again, and three were
survivors. Each gained a test, or lost code that could not matter.

**Opening the same file again** plays the previous decode of each sample,
the same audio under the same id, until the reload lands and the feed
builds again. It is harmless, and it is why the load test opens in a fresh
window.

**Looked at**: a loop drawn over bars 2 to 3 and playing from bar 2. Pause
icon showing, loop lit, the readout at 2.3.538, the band filled in the
ruler and faint behind the lanes with the playhead inside it.

The phase adds 74 tests. The suite is 2094: 32.0 s serially, 9.4 s in
parallel, 4.2 s in the fast lane.
