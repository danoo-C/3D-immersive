# M3 · Phase 10 — The master meter, and the arrangement heard

**Status:** not started · **Plan:** not written yet

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

**Out:** per-channel meters, deliberately never (D-55). The limiter that
would keep the meter out of the red → M4.

## Acceptance

- [ ] The meter reads the engine's bus peaks at frame rate, and a stand-in
      feeding a known level draws that level.
- [ ] A peak holds for 1.5 s and then falls — asserted against a clock the
      test controls.
- [ ] A sample over 0 dBFS latches the clip indicator in `warn`, marked by
      more than colour alone, until the indicator is clicked.
- [ ] The meter sits left of the notice count, and the xrun counter beside
      it, as `04`'s *Accessibility and feel* orders them.
- [ ] `meter` is in `04` and the bundled theme, and the meter names no hex.
- [ ] A screenshot of the meter holding a peak, and latched, is taken and
      looked at.
- [ ] **Heard**, on native Windows or Linux rather than WSL: an arrangement
      of at least three channels, built in the window from imported samples —
      moved, trimmed, split and faded — plays back as arranged, loops
      cleanly, clicks at no split, and the meter moves with it. The machine,
      device and block size are recorded in the Notes. The milestone's own
      acceptance is that a person hears this, and only a person can tick
      this box.

## Implements

F-54, D-55 — *Master meter* in [04-ui-spec.md](../04-ui-spec.md),
*Metering* in [05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
