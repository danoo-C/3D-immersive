# M3 · Phase 10 — The master meter, and the arrangement heard

**Status:** built — **waiting to be heard** · **Plan:** [plans/phase_10_meter_and_listening.md](plans/phase_10_meter_and_listening.md)

## Goal

The status bar shows a stereo peak meter left of the notice count: two
narrow bars, a peak that holds for 1.5 s, and a clip indicator that latches
in `warn` until it is clicked (F-54). Then the milestone's acceptance is met
the only way it can be — by a person who builds an arrangement in the
window and hears it play back flat on native Windows or Linux.

## Scope

**In:** the meter widget, `ui/widgets/meter.py` in
[02](../02-architecture.md)'s layout, reading the bus peaks phase 8 writes;
peak hold and decay; the latched clip indicator, cleared by a click; its
place in the status bar, in the order `04` gives; the `meter` group; the
listening test, and a record of the machine it ran on.

**Out:** ~~per-channel meters, deliberately never (D-55)~~ - in, see
below. The limiter that would keep the meter out of the red → M4.

**Amended before the phase started (2026-09-26).** Per-channel meters were
asked for as the plan was written: a thin level meter in each channel
header, showing what that channel adds to the bus, with the master meter
still the one clip light (F-60, D-117, superseding D-55). The same widget
draws both, and the engine publishes both. Their movement is D-118's. Three
acceptance lines are added below for them, marked as added.

## Acceptance

- [x] The meter reads the engine's bus peaks at frame rate, and a stand-in
      feeding a known level draws that level.
- [x] A peak holds for 1.5 s and then falls — asserted against a clock the
      test controls.
- [x] A sample over 0 dBFS latches the clip indicator in `warn`, marked by
      more than colour alone, until the indicator is clicked.
- [x] The meter sits left of the notice count, and the xrun counter beside
      it, as `04`'s *Accessibility and feel* orders them.
- [x] `meter` is in `04` and the bundled theme, and the meter names no hex.
- [x] A screenshot of the meter holding a peak, and latched, is taken and
      looked at.
- [x] *Added.* Each channel header shows a meter of what that channel adds
      to the bus: a stand-in playing a known level on one channel at a
      known gain draws that level there, and a muted channel's meter falls
      to nothing.
- [x] *Added.* A channel meter has a peak hold and no clip light; a
      channel driven past full scale lights only the master's.
- [x] *Added.* A screenshot of a real arrangement playing, with the
      channel meters moving at different levels, is taken and looked at.
- [ ] **Heard**, on native Windows or Linux rather than WSL: an arrangement
      of at least three channels, built in the window from imported samples —
      moved, trimmed, split and faded — plays back as arranged, loops
      cleanly, clicks at no split, and the meter moves with it. The machine,
      device and block size are recorded in the Notes. The milestone's own
      acceptance is that a person hears this, and only a person can tick
      this box.

## Implements

F-54, F-60, D-117, D-118 — *Master meter* in [04-ui-spec.md](../04-ui-spec.md),
*Metering* in [05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.

**Built (2026-09-26).** Five steps, with the plan's layers as they stood:
the engine's peaks per channel, the ballistics, the widget, and the
window's tick feeding both. Four things the tests found:

- **A stereo channel read its left side twice** under one mutation, and no
  test noticed, because every channel in the tests was mono. There is a
  stereo one now.
- **A loop-bound spy** in the window tests called the last header's `feed`
  for every header, until ruff's B023 pointed it out. A test that watches
  the wrong thing passes for the wrong reason.
- **The notice count hides at none**, so its position read 0 and the order
  test could not see it. The test posts a notice first.
- **mypy narrows an attribute across two asserts**, as it does a property,
  so the latch is read through a helper.

Looked at with the person's 23 stems in parallel channels, playing through
the stand-in from 1:15. Each header's meter stood at its own level: DRUMS_2
at −5.7 dB with its hold, *vocal* at −10.7, *fx* at −30, and the nine
stems silent there empty. The master ran into its hot zone and latched
its `!`. Twenty-three stems at 0 dB each sum past full scale. That is a
true report about the mix, and M4's limiter and each channel's gain field
are its answer. Twenty-seven mutations over the four steps, all caught; one
only after the stereo test was added. The phase adds 27 tests, and the
suite is 2219: 13.7 s in parallel, 5.9 s in the fast lane.

### ⚠️ To tick the last box — and M2 phase 7's with it

On a native Windows or Linux machine, with headphones:

1. On Linux, `sudo apt install libportaudio2`. Windows needs nothing extra.
2. `python3 launch.py --install --run`. With a device or block size in
   mind: `python3 launch.py --install --run -- --device "Headphones" --block 512`.
3. **M2 phase 7's box first.** File › Import Folder…, pick a folder with a
   44.1 kHz WAV and an MP3, and double-click each. Both should play at their
   own pitch and speed, and `Esc` should stop either.
4. **This box.** Import the stems. Drop at least three onto the timeline,
   *In Parallel*. Move one, trim one, split one with `S` at the playhead, and
   give one a fade in the parameters pane.
5. Play it. It should play as arranged, and click at no split. The master
   meter and each channel's should move with what is heard.
6. Draw a loop over a bar or two in the ruler, and let it go round a few
   times: no gap, and no click at the turn.
7. Record here the machine, the OS, the device and the block size, and
   what was heard. Then tick this box, and phase 7's, and M3 and M2 can be
   marked complete.
