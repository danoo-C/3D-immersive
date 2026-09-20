# CI

`ci.yml` runs lint, format check, type check and tests on Linux, macOS and
Windows against Python 3.11 and 3.13 — the ends of the supported range.

Two things worth knowing before editing it:

- **`QT_QPA_PLATFORM: offscreen`** is set for the whole workflow. Without it
  every Qt test fails on a headless runner.
- **The Linux apt step is not optional.** PySide6 wheels dynamically link
  against system Qt dependencies, and `libEGL.so.1` in particular is missing
  from `ubuntu-latest`. The failure looks like an unrelated import error.

CI cannot test audio. There is no device on a runner, and N-1 is a latency
requirement that a shared CI machine could not measure meaningfully anyway.
Preview and the M4 benchmark are verified by hand, per platform, per milestone.
