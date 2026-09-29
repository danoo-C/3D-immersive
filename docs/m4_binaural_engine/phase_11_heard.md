# M4 · Phase 11 — Heard

**Status:** not started · **Plan:** not written yet

## Goal

The milestone's acceptance, met the only way it can be: a person on
headphones, on native Windows or Linux. Three things are to be heard. The
crossfade's A/B, the roadmap's named test. A choice among candidate HRTF
sets, which is QA-30's listening test and settles the bundled default. And
positions set numerically in a test project, heard where they were set.
Everything that can be prepared is: renders written to WAV by a test
helper, a test project, and a checklist.

## Scope

**In:** the renders, written from the engine exactly as it plays: the 440 Hz
sawtooth orbiting at 1 rev/s with and without the crossfade, and the same
orbit and a front-to-back sweep through each candidate set that can be
bundled; a test project with sources at named positions; the listening
checklist; the verdicts, recorded; the default set changed if the listening
says so.

**Out:** anything the listening finds wrong → the phase it belongs to,
reopened, with the finding in its Notes.

## Acceptance

- [ ] The renders and the test project exist, and each render's
      measurements are recorded beside it (sidebands for the crossfade pair,
      level and ITD at the named positions).
- [ ] **Heard**: the crossfaded orbit has no buzz, and the pair can be told
      apart. If they cannot, the crossfade is not running.
- [ ] **Heard**: the candidate sets compared, a default chosen, and its
      name, version and licence recorded as QA-30's resolution.
- [ ] **Heard**, in the application on native Windows or Linux: each source
      in the test project is where its position says - front, behind, left,
      right, above - and the benchmark's live xrun count over a minute of
      32 moving sources is zero. The machine, device and block size are
      recorded.

## Implements

The roadmap's named crossfade test, QA-30, and M4's *Done when*.

## Notes

Appended while building.

**The live count, from phase 10.** Run on the listening machine, from the
repository:

```
.venv\Scripts\python -m immersive.benchmark live     # Windows
.venv/bin/python -m immersive.benchmark live         # Linux
```

It opens the application's window on the output the application would use,
taking `--device` and `--block` as the application does. It plays 32
sources, each moving on an orbit, for a minute, then prints the machine,
the device and its host API, the block, PortAudio's latency, and the
engine's xrun count, which is what PortAudio reported. **Hands off, the
count must be 0**: that is this phase's acceptance line.

Run it twice more with `--load scrolling` and `--load repainting`. The
window then scrolls the timeline, or repaints itself without pause, with
nobody at it. Those counts are recorded but not held to zero. Phase 10
found that the audio thread waits for the GIL at every numpy call (D-137),
so a busy UI costs it blocks, and these two runs say how much on the
machine that matters. `python -m immersive.benchmark blocks` gives N-1's
timings there too.
