# M4 · Phase 10 — The benchmark, and the switch interval

**Status:** in progress · **Plan:** [plans/phase_10_benchmark.md](plans/phase_10_benchmark.md)

## Goal

N-1 is measured, not argued: **32 moving sources at a 512-frame block**,
the finished graph with distance, crossfade, bypass and the limiter all
running. It is done here as timings with a margin, and on the listening
machine as a live xrun count. `sys.setswitchinterval(0.001)` is set in
`app.py` before the stream opens (D-39), and measured the way the roadmap
insists: while the UI is actively repainting, since an idle UI shows no
difference and proves nothing.

## Scope

**In:** a benchmark script and a test that runs a short form of it; `p50`,
`p99` and worst per-block times for 1, 8, 16 and 32 sources, a source
being a slot, so a paired channel counts two (phase 9), and for 32 paired
channels, 64 sources, recorded beside them; a stand-in
audio thread calling `process` on a real-time schedule while the window
repaints offscreen, counting missed deadlines with and without the switch
interval; the switch interval itself; what the live count must be, written
into phase 11 for the listening machine.

**Out:** optimising past N-1 → only if it fails (05, *If Python is not
enough*).

## Acceptance

- [ ] 32 moving spatial sources at 512 frames take a p99 per-block time
      under half the 10.7 ms budget on this machine, recorded with the
      machine's name.
- [ ] The short form runs in the suite and fails if p99 passes 60% of the
      budget - loose enough for a loaded machine, tight enough to catch a
      regression of kind rather than degree.
- [ ] With the UI repainting continuously, the stand-in audio thread misses
      fewer deadlines with the switch interval than without it, both
      counts recorded. If it does not, D-39 is reopened with the numbers.
- [ ] `app.py` sets the switch interval before any stream opens, tested.

## Implements

N-1, D-39 - *Cost estimate*, *Realtime safety checklist* and *If Python is
not enough* in [05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
