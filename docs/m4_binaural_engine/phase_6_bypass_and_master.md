# M4 · Phase 6 — Bypass and the master bus

**Status:** ✅ complete · **Plan:** [plans/phase_6_bypass_and_master.md](plans/phase_6_bypass_and_master.md)

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

- [x] A bypassed stereo channel at centre comes out bit-identical to its
      samples at unity gain, and never passes through a transform.
- [x] A mono bypassed channel panned hard left is silent on the right, and
      centred it is −3.01 dB on each side.
- [x] Master gain moves the whole bus, ramped across one block.
- [x] With the limiter on, no output sample passes −0.3 dBFS, whatever the
      input. A signal that never reaches the knee comes out equal to its
      input, delayed by exactly the engine's stated latency, 72 frames, and
      by the same with the limiter off, so switching it moves nothing in
      time (D-124). *Amended while planning: as first written this said
      "not delayed", compensated inside. A lookahead cannot be had without
      the delay unless the graph renders ahead of its output, which the
      spatial path's block-sized transform cannot do at a seek. And "the
      ceiling" became "the knee": a 2 dB soft knee centred on the ceiling
      starts turning a signal down 1 dB below it.*
- [x] With the limiter off, a signal past full scale passes untouched, and
      the master meter latches.
- [x] The zero-allocation test holds with bypassed channels and the limiter
      running.

## Implements

D-32, D-41 (its precondition), D-54 - *HRTF bypass* and *The master bus* in
[05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.

**Built (2026-09-27).** Pan is per clip (D-125). The lane keeps mono clips in
a row of their own, and a channel's gain is four factors: a mono clip to each
ear, and a stereo clip's two sides. The UI thread works them out, pan law and
balance included. Only a bypassed channel's differ, so no channel that was
not bypassed changed by a sample. The master's gain and switch sit in the
snapshot and change by a generation-tagged `MASTER` (D-126). The first
snapshot sets them rather than ramping from unity. Writing its test found a
project opened at −6 dB ramping down across its first block.

The limiter (D-123) was prototyped while planning and measured before it was
decided. Porting it, the knee came out wrong: it started 2 dB under the
ceiling instead of 1, and took the excess from the ceiling instead of from
the knee's top, so it limited at −1.3 dBFS. That was still brickwall, so the
ceiling tests passed. The static curve caught it, and so did the output that
should have been the input below the knee. D-123's own wording, "a knee whose
top is the ceiling", invited it, and is corrected to say the knee is centred
on the ceiling and its top comes out there. Without the 10⁻⁵ dB margin,
noise at +12 dBFS put samples just past the ceiling at every block size.

The limiter's block time, hot noise and quiet, on its own:

| Block | Budget | Mean | 99th percentile |
|---|---|---|---|
| 256 | 5.3 ms | 31–42 µs | 102–121 µs |
| 512 | 10.7 ms | 36–53 µs | 79–179 µs |
| 2048 | 42.7 ms | 57–59 µs | 92–102 µs |

The ranges are quiet noise and noise at +12 dBFS. Nothing in it depends on
how loud the signal is, so the difference is WSL's noise, not the limiter's.
Next to the spatial path's 1.47 ms for 32 sources it is small.

**The latency (D-124)** moved 80 tests. They read the engine's output sample
for sample, and all of it was now 72 samples later. `tests/hearing.py` reads
it back on the timeline as a render will: a test plays first and reads after,
and a read plays on as far as the latency still holds back. The graph's and
the spatial path's tests run with the limiter off, since some of their
signals are at full scale and they are about what reaches it. The stand-in's
ramp now stays under half scale. The master meter's clip light can only
latch with the limiter off, so that test switches it off, and a new one
checks that with it on, 1.5 at full scale comes out under the ceiling while
the channel's own meter still reads 1.5. A stopped meter needs one block
more to fall: the first block after a stop still carries the 1.5 ms the
lookahead held back.

**The zero-allocation test** gained a bypassed mono and a bypassed stereo
channel, both panning, the master moving under +12 dB so the limiter reduces
every block, and the switch fading off and on: nothing kept, 1308 bytes at
most. The ring's read count passes 256 and keeps 32 bytes once, as the
test's own comment had recorded. With pan and the master sent too, that fell
in block 466, inside what is counted, where it had been in block 1028. So
the counts are taken past 256 before the measure starts.

`test_player` runs the engine at 64 frames, shorter than the lookahead. The
limiter is correct there: numpy copies the overlapping history through a
buffer. That allocates, but only a test or an offline render asks for such a
block. A device's block is at least 256 frames.

**A flaky test found on the way**, not this phase's. It failed once in a
suite run during step 1 and once in 15 after step 2:
`test_a_request_replaced_is_never_handed_over_late`, phase 4's. Its stand-in
holds whichever call reaches it first, and both requests were queued at once
on two workers. When the second request's worker called first, the current
request was the one held, and the bank never came within ten seconds. The
test now waits until the first request is held before asking again. The race
was reasoned out from the failure, "never happened" after the full wait, and
not forced. Eight runs of its file under load since were clean.

Twenty-five mutations, all caught: the plan's nineteen and six more. The
phase adds 45 tests; the suite is 2392.
