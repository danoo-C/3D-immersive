# M4 — Binaural engine

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Specification: *The HRTF
pipeline*, *Per-block processing*, *HRTF bypass*, *The master bus*,
*Parameter smoothing* and *Realtime safety checklist* in
[05-audio-engine.md](../05-audio-engine.md); `Position`, `HrtfRef`,
`Distance` and `Master` in [03-data-model.md](../03-data-model.md); the
channel and project views of the *Parameters pane* in
[04-ui-spec.md](../04-ui-spec.md); *Threading* in
[02-architecture.md](../02-architecture.md) · Spike:
[s0_listening_spike/](../s0_listening_spike/README.md) · Workflow:
[09-workflow.md](../09-workflow.md)

| Phase | Status |
|---|---|
| [1 — The HRTF set](phase_1_hrtf_set.md) | ✅ |
| [2 — ITD and minimum phase](phase_2_itd_minimum_phase.md) | ✅ |
| [3 — Directions](phase_3_directions.md) | ✅ |
| [4 — The bank, and its cache](phase_4_bank.md) | ✅ |
| [5 — The engine, spatial](phase_5_spatial_engine.md) | ✅ |
| [6 — Bypass and the master bus](phase_6_bypass_and_master.md) | ✅ |
| [7 — The spatial fields](phase_7_spatial_fields.md) | ✅ |
| [8 — Level as mixed](phase_8_level_as_mixed.md) | not started |
| [9 — The benchmark, and the switch interval](phase_9_benchmark.md) | not started |
| [10 — Heard](phase_10_heard.md) | not started |

The order is dependency order, and it is the spike's order. The spike
proved the pipeline by ear (S0), and this milestone rewrites it properly in
`audio/hrtf/`. It keeps the spike's phase notes as the record of what was
learned the hard way, and moves nothing across from `spikes/`.

The first four phases are the pipeline, each headless and each tested
against numbers the spike measured: a set loaded and normalised, then split
into delay and spectrum, then made queryable by direction, then prepared as
a bank. The fifth puts it on the audio thread, the sixth adds the paths that
skip it and the bus everything lands on, and the seventh gives the pane the
fields that make it audible. The eighth makes a placed stem keep the level
it was mixed at. The benchmark is ninth because it measures the finished
graph, and hearing is last because only a person can do it.

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> positions set numerically in a test project are audibly, correctly
> placed — and the benchmark passes. If it does not pass here, we find out
> now, with the port seam still tiny, rather than after the UI is built on
> top.

## Starting with M2's and M3's last boxes open

M2 and M3 are built. Each waits only on a person listening on native
Windows or Linux, and both are one sitting (M3 phase 10's Notes). Nothing
here rests on those boxes: the flat engine this milestone extends is tested
headless. M4's own last phase needs the same machine, and the same
headphones.

## Scope amended during the milestone

**Phase 8, level as mixed, was added after phase 7** (2026-09-27), from a
user issue: [3d-sensitivity](../user-issues/3d-sensitivity/level-as-mixed.md).
Listening to phase 7's fields found a placed stem at the default position
14 dB louder than itself and distorting, and every direction and every
stereo stem at a level nobody chose. The benchmark and hearing moved to 9
and 10, since the one should measure and the other hear what ships.

## Scope amended before the milestone started

**The position fields move here from M5.** M4's acceptance is positions
*set numerically* and heard, and without the pane's X, Y and Z fields the
only way to set one is to edit the `.3dim` by hand. The fields exist
already, drawn disabled and naming M5 (M3 phase 7). They go live here, one
edit per change, and M5 keeps what is its own: the views, dragging on them,
and the fields' two-way binding to a drag. The roadmap's M5 line is struck
through and says where it went.

**QA-24 in the roadmap's first bullet is QA-30.** QA-24 is the fixed
listener. The default dataset is QA-30's, "pick by listening test during
M4". Corrected in the roadmap.

## Questions the plans must settle

Found while writing the phase docs, and left open on purpose. Each is its
phase's first decision.

- **How does the default set ship?** The SOFA as published is 36.6 MB,
  Apache 2.0, 8802 directions of 256 taps. The choice is between that file
  as it is, or a derived file holding only what the pipeline reads. And
  where it lives, since the repository does not hold it today. (Phase 1.)
- **SOFA's axes against the project's.** SOFA's listener faces +x with +y
  to the left. The project's faces +Y with +X to the right (03). One mapping,
  tested at the four cardinal points and at the poles. (Phase 1.)
- **How does a position reach the audio thread?** A position is per
  channel and changes by edits now, and by automation at M6: in the
  snapshot, or through the command ring as gain does (D-105). (Phase 5.)
- **The limiter's algorithm**, inside D-54's fixed design: a ceiling of
  −0.3 dBFS, 1.5 ms of lookahead compensated internally, 50 ms release and
  a 2 dB knee. (Phase 6.)
- **What "zero xruns" can mean on WSL.** N-1's benchmark is timings with a
  margin here. The live count, with the UI repainting, is the listening
  machine's. (Phase 9.)

## What this milestone does not deliver

| Not here | Where |
|---|---|
| Loading a SOFA of one's own (F-27's other half) | M8, with Preferences; the loader built here takes any path, and the pane shows the built-in |
| The top and front views, dragging a source | M5 |
| Positions that move by themselves | M6: automation. M4's sources move by edits, and in its tests and renders by a trajectory the test gives |
| Air absorption | not in v1 (D-22) |
| Rendering to a file | M7; M4's listening renders are written by a test helper, not by File › Render |

## Notes

Appended as phases complete.

**Phase 1.** A SOFA set loads into an `HrirSet`: directions in the
project's axes, converted here and nowhere else; responses at 48 kHz,
normalised to S0's 0.25 per ear; the file's own licence. SADIE II D1 is
fetched at install and checked by SHA-256, following 02 and 08's *fetched,
not committed* over a 14 MB derived file that was measured and rejected.
Twenty-eight mutations, all caught.

**Phase 2.** Each measurement split into a signed ITD and a minimum-phase
response, S0's construction ported with S0's numbers: 99.99% far-ear
agreement, the largest ITD 38.3 samples on the interaural axis. Checking
every response rather than S0's twenty found that the magnitude holds to
0.019 dB within 30 dB of each peak, but not at the floors of notches 80 dB
down, which 256 taps cannot carry. The acceptance was amended to say so.

**Phase 3.** A direction is located on the audio thread without allocating
(D-119): a cube map of sampled cells and a walk across shared edges, in
place of S0's KD-tree, which returns new arrays on every query. 3.5 µs a
direction, 215 µs for 32 sources, and the ITD continuous as S0 measured.

**Phase 4.** The bank, and a cache of what is slow to make rather than of
the bank itself (D-120). SADIE II D1: 6.4 s cold, 0.23 s warm, from one
21 MB entry for every block size. The application prepares it on a worker
with an activity. Only a real launch or an open asks for it, so no test
that builds a window pays for it. The pipeline is complete and headless;
phase 5 puts it on the audio thread.

**Phase 5.** Every channel that is not bypassed is heard through the HRTF,
summed over sources in the frequency domain, without allocating. A position
reaches the engine as a gain does, in the snapshot and by a `POSITION`
command (D-121), and the path is float32 end to end because numpy 2's
default FFT is not (D-122). 32 moving sources take 1.47 ms a block at 512
frames against 10.67 ms, and the crossfade cuts the block-rate sidebands by
32.2 dB, where S0 cut them by 33.7. The sweep found a real bug in phase 3's
lookup, now fixed: an index read its resolution from a constant.

**Phase 6.** A bypassed channel is placed by pan: the constant-power law for
its mono clips and the balance for its stereo ones, applied per clip since a
channel may hold both (D-125). Everything then passes the master gain and
D-54's limiter, brickwall by construction and computed a block at a time
without a loop per sample (D-123). The master gain and the limiter's switch
travel as channel gains do (D-126). The lookahead is a latency the engine
states, 72 frames whether the limiter is on or off, which a render drops
(D-124). That was the one acceptance line amended: "not delayed" could not
be had without the graph rendering ahead of itself.

**Phase 7.** The pane's position, pan, rolloff, master gain and limiter are
live, one edit each, and heard at the next block. The tests type into the
pane of a window playing through a synthetic head, and listen. With several
channels, position is live while any is placed and goes to all of them on
the axis typed (D-127). Only the HRTF set is still drawn dead, naming M8.
