# Handoff — 2026-09-27, end of the day

To continue, tell Claude: **"read HANDOFF.md and start M4 phase 10"**.
Delete this file, `handoff_sweep.py` and `handoff_blocktime.py` when phase 10
closes, as the phase 5 handoff was deleted when phase 5 closed.

## Where things are

- **Branch:** `m4-binaural-engine`. Everything is committed locally. Push it
  if you have not: at the time of writing it was 7 commits ahead of
  `origin`, all of phase 9 plus this handoff.
- **M4:** phases 1 to 9 are ✅. Phase 10, the benchmark, is next, and its
  plan is not written yet. Phase 11, hearing, is yours.
- **Suite:** 2512 tests pass, and ruff and mypy are clean. CI has never run,
  because of the GitHub account's billing lock, so "green" means locally.

## What was done today

| Phase | What it gave you |
|---|---|
| 5 — The engine, spatial | channels heard through the HRTF, moving, without allocating |
| 6 — Bypass and the master bus | pan and balance for bypassed channels, master gain, the limiter (D-123 to D-126) |
| 7 — The spatial fields | the pane's position, pan, rolloff, master and limiter fields live (D-127) |
| 8 — Level as mixed | a stem as loud as it was mixed wherever it is placed, and no distortion at (0, 0, 0) (D-128 to D-131). You heard it: "exactly what I imagined" |
| 9 — Stereo placement | a stereo channel's left and right as two sources, free or linked in symmetry (D-132 to D-135). You heard it: "really trippy, I love it" |

The two issues you raised are both confirmed:
[docs/user-issues/README.md](docs/user-issues/README.md) has the index and
the progress bars.

## Where every spatial setting is set (D-135)

The answer to this session's title. One home each, in the parameters pane.
The views (M5) and automation (M6) will move the same values, not keep
their own.

| Where | Settings |
|---|---|
| **Project view** (select nothing) | HRTF set (shown; chosen at M8), distance rolloff, master gain, limiter, Level as mixed |
| **Channel view**, top | gain, mute, solo, HRTF bypass, pan (only while bypassed) |
| **Channel view**, **Placement** | Mode (One point / Free / Linked), Position or Left and Right X/Y/Z, Pivot X/Y/Z, Mirror X/Y/Z, Mono as two sources |

The full description is in
[docs/04-ui-spec.md](docs/04-ui-spec.md#placement).

## Next: M4 phase 10, the benchmark and the switch interval

The phase doc is
[phase_10_benchmark.md](docs/m4_binaural_engine/phase_10_benchmark.md), and
the plan is to be written first, as every phase's is. What it has to know:

- **Count sources, not channels.** A paired channel is two sources. Record
  32 pairs (64 sources) beside the 1, 8, 16 and 32 sources the acceptance
  names. The phase doc says so already.
- **Numbers so far**, SADIE at 512 frames, 3000 blocks, from
  `handoff_blocktime.py`:
  - 32 points: 1.40 ms mean, 2.52 ms p99.
  - 32 linked pairs: 3.15 ms mean, 5.16 ms p99.

  The acceptance is a p99 under half the 10.67 ms budget (5.33 ms) for 32
  sources. 32 pairs sit just under that line, but the line is for 32
  sources, not 64.
- **The switch interval (D-39)** is measured while the UI repaints, with a
  stand-in audio thread counting missed deadlines, with and without
  `sys.setswitchinterval(0.001)`. An idle UI proves nothing.
- **Run with level as mixed on.** That is what a project has.
- **Timings are noisy on this machine**, ±1–2 s on the suite. Compare
  states by interleaved runs. A single slow block, 11 ms once, happened on a
  point run and a pair run alike: that is WSL, not the graph.

## How the work is done

- **Phases are built end to end:** plan, decisions, steps, mutation sweep,
  close, without check-ins, and the decisions are reported after. Commits
  are local, and you push.
- **A commit waits for pytest's exit code**, not its tail.
- **Stage by path**, never `git add -A`. Inside Claude's sandbox,
  `git status` shows untracked `.bashrc`, `.gitconfig`, `.claude/` and so on
  in the repo root. They are `/dev/null` placeholders the sandbox makes, not
  files, so leave them alone.
- **Mutations are named in the plan before the tests**, and run with
  `handoff_sweep.py`. It flags a mutation that breaks the build as "broken,
  not caught", and it keeps every run's output in `$TMPDIR/sweep-runs`. To
  reuse it, replace its `M` and `LATER` lists.
- **Your stems** are in `test-samples/`, gitignored. Real-stem numbers are
  measured on the loudest 12 s of each.

## Loose ends

- **A flake, not yet understood.** During phase 9's sweep, two of the 22
  runs also failed a test in `tests/test_parameters.py` that the phase does
  not touch: `test_a_sample_shows_its_file_its_facts_and_its_waveform` once,
  and `test_the_audition_button_plays_the_sample` once. They did not fail
  again in any retry. If it recurs, read the message in `sweep-runs` before
  guessing.
- **A mono channel's Mode reads "Linked"** but does nothing until "Mono as
  two sources" is ticked. This is deliberate, and in phase 9's Notes. Say if
  it confuses you when you use it.
- **For M5:** each pair is to be drawn as two linked points, and the side
  you grab should lead. Today the left always leads, and a switch from Free
  to Linked keeps the left and snaps the right to its mirror.
- **For M6:** automation's keys are `pos.*`, `gain` and `pan` today. The
  right side's keys and the pivot's are added then.

## For phase 11, when you listen

Phase 11 prepares renders, a test project and a checklist. Worth trying in
the application meanwhile:

- a stereo stem as a linked pair, with Left X moved slowly from 0 to −2;
- the same stem Free, with one side walked behind you;
- Mirror Y on with X off: the image front and back;
- Level as mixed off and on, at 3 m. **Turn your headphones down before
  trying it off at (0, 0, 0)**: that is 14 dB louder, as the distance law
  says, and only the limiter holds it.
