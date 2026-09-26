# M4 · Phase 6 — Bypass and the master bus

**Status:** not started · **Plan:** not written yet

## Goal

A channel with HRTF bypass skips the spatial path entirely: its stereo is
kept, a pan law or a balance places it, and it joins the bus after the
inverse transform (05, *HRTF bypass*). Everything then lands on the master
bus, which applies the project's master gain and, while it is on, the fixed
limiter (D-54): a brickwall ceiling at −0.3 dBFS, with 1.5 ms of lookahead
that it compensates itself, so the master stays aligned with the stems M7
will render around it.

## Scope

**In:** bypassed channels' stereo reads; the constant-power pan law for
mono, and the balance for stereo that leaves a centred source
bit-transparent; the pan as a gain that ramps; the master gain and its ramp;
the limiter and its compensation; the bus meter reading after the limiter.

**Out:** the fields that set pan, master gain and the limiter → phase 7.

## Acceptance

- [ ] A bypassed stereo channel at centre comes out bit-identical to its
      samples at unity gain, and never passes through a transform.
- [ ] A mono bypassed channel panned hard left is silent on the right, and
      centred it is −3.01 dB on each side.
- [ ] Master gain moves the whole bus, ramped across one block.
- [ ] With the limiter on, no output sample passes −0.3 dBFS, whatever the
      input. A signal that never reaches the ceiling comes out equal to its
      input and **not delayed**: the lookahead is compensated inside.
- [ ] With the limiter off, a signal past full scale passes untouched, and
      the master meter latches.
- [ ] The zero-allocation test holds with bypassed channels and the limiter
      running.

## Implements

D-32, D-41 (its precondition), D-54 - *HRTF bypass* and *The master bus* in
[05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
