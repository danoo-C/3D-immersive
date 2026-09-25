# M3 · Phase 9 — Transport

**Status:** not started · **Plan:** not written yet

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
plan decides; seeking by clicking the ruler during playback; the loop region,
dragged in the ruler and drawn in the `loop region` group, looping exact to
the sample; the playhead readout, in bars.beats.ticks or minutes:seconds,
drag-scrubbable and typeable with phase 2's numeric field; the xrun counter
(`04`, *Accessibility and feel*); a device lost mid-playback stopping the
transport, holding the playhead and saying so (`05`, *The output stream*);
audition's place beside the transport, as the plan decides; `Esc` clearing
the selection only while stopped.

**Out:** the meter → phase 10. What a real device sounds like → phase 10.
Render ranges built on the loop region (F-53) → M7.

## Acceptance

- [ ] `Space` starts playback from the playhead and pauses where it is,
      `Esc` stops, and `Enter` returns the playhead to the start — asserted
      through a stand-in stream, on what the engine is asked to do.
- [ ] During playback the drawn playhead is where the engine last said it
      was, updated at frame rate.
- [ ] With a loop region dragged in the ruler and looping on, playback runs
      from its start to its end and continues from its start with no gap and
      no repeated sample — asserted on the samples the stand-in receives.
- [ ] The readout shows the playhead in the ruler's unit, and a position
      typed in either unit moves it (F-52).
- [ ] Clicking the ruler during playback seeks there.
- [ ] The xrun counter is quiet at zero and drawn in `error` once there is
      one.
- [ ] A device lost during playback stops the transport, leaves the playhead
      where it was, and posts one notice.
- [ ] A double-click in the pool during playback does what the plan
      decides, and the Notes say why.
- [ ] Every transport action and the readout are live, and no tooltip in
      the window names M3 any longer.

## Implements

F-19 (the readout's unit), F-20, F-52, D-63 — *Transport and the ARM
toggle*, *Keyboard* and *Accessibility and feel* in
[04-ui-spec.md](../04-ui-spec.md), *The output stream* in
[05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
