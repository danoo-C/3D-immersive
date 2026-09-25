# Test speed — plan

**Status:** steps 1–2 done, 3–6 proposed · **Written:** 2026-09-24 ·
**Measured at:** `d005e34` on `m2-media`, WSL2, 12 logical CPUs, Python 3.13

## Progress

| | Serial | Parallel (8, `worksteal`) |
|---|---|---|
| Before | 15.5 s | — |
| ~~Step 1~~ landed | **11.3 s** | — |
| ~~Step 2~~ landed | 11.3 s | **5.3 s** |

Both measured after landing, three parallel runs in a row, all green. The
commands now live in [08-environment.md](../08-environment.md)'s *Checks*
and the sweep practice in [09-workflow.md](../09-workflow.md); this document
keeps only the argument and the remaining steps.

This document owns one thing: the plan for making the test suite faster, and
the measurements it is argued from. It is not part of the numbered canon. What
the suite *tests* belongs to the phase docs, and how to run it belongs to
[08-environment.md](../08-environment.md). Once a step lands, the fact it
establishes moves to its proper home and the step here is struck through.

## Where it stands

| | |
|---|---|
| Tests | 1078, all passing |
| Serial wall time | **15.8 s** (pytest reports 15.5 s) |
| Collection | 1.0 s |
| Headless tests | 877 — **3.0 s** in total, about 3.4 ms each |
| GUI tests | 201 — **10.1 s** in total, about 50 ms each |

The suite has been worse. Until M2 phase 1 every window a test built stayed
alive for the rest of the session, and each new one re-polished all the old
ones, so it took 185 s. An autouse fixture now frees them, and the Notes of
[M2 phase 1](../m2_media/phase_1_project_in_the_window.md) describe the leak.
**This plan is about what is left.**

**19 % of the tests take 77 % of the time.** They are the GUI tests, and
more than half of each one's cost is setup, which here nearly always means
building a `MainWindow`.

### What building a window costs

Measured by constructing ten windows in a row, after one to warm up:

| | |
|---|---|
| One `MainWindow()` | **57–64 ms** |
| …of which `restore_theme()` → `apply_theme()` | 36 ms |
| …of which `QApplication.setStyleSheet()` alone | 23 ms |
| …of which building the splitter layout | 18 ms |

`restore_theme()` runs at the end of every window's construction. When no
theme has been chosen, which is every test and most launches, it re-applies
the built-in theme. `build_application()` has already applied that exact
stylesheet, and Qt re-polishes every widget on every `setStyleSheet` call,
even an identical one. So half of each window's cost is repainting it in the
colours it already has.

### The slowest single tests

| Time | Test | Why |
|---|---|---|
| 589 ms | `test_curves.py::test_every_value_stays_inside_the_convex_hull_…` | 5 000 random curves, evaluated in Python |
| 384 ms | `test_commands.py::test_a_thousand_edits_undo_back_…` | a thousand edits; the count is the point |
| 285 ms | `test_theme_menu.py::test_importing_the_ui_makes_no_directory` | starts a fresh interpreter, which is the point |
| 222 ms | `test_audition.py::test_loading_the_backend_never_raises` | tries to import `sounddevice`, which fails slowly without PortAudio |
| 212 ms | `test_theme_switching.py::test_the_built_in_survives_a_new_window` | builds two windows |
| 181 ms | `test_import.py::test_the_window_keeps_turning_while_an_import_runs` | sleeps 150 ms per file on purpose |

Four import and loading tests sleep deliberately, 0.1–0.15 s each, to keep
workers busy for long enough to observe. That is about 0.5 s of the run.

## The plan

Six steps, ordered by payoff over risk. Every number marked *measured* was
produced before this plan was written, by applying the change temporarily
and running the whole suite; nothing in the repository has been changed yet.

### ~~1. Stop re-painting a window in the colours it already has~~ — done

**Measured: window construction 64 → 32 ms; serial suite 15.5 → 12.0 s**
before landing, **11.3 s** after.

`MainWindow.apply_theme()` returns early when the theme it is asked to apply
is already active *and* the application's stylesheet is already that theme's.
Only the first matters in practice, since `restore_theme()` on a fresh window
is the only caller that asks for the current theme. The check is a string
comparison of about 6 KB, against 23 ms of re-polishing.

It helps real launches as much as tests: the application currently paints
its first window twice.

- [x] `apply_theme` skips a theme that is already applied.
- [x] A test asserts that the skip happens — the stylesheet is not set again
      for the same theme — and that switching to a *different* theme still
      runs D-82's full order. The order test in `test_theme_switching.py` must
      pass unchanged.
- [x] A named mutation: removing the skip is caught by the first test, and
      skipping a genuinely different theme is caught by the existing ones.
      *Landed as two mutations: the skip removed, and skipping on the theme
      alone without comparing sheets. Each is killed by the test written for
      it; the second needed its own test, which puts the application in the
      active theme but another theme's sheet.*
- [x] Measured again after landing, with the result recorded here: 11.3 s.

All 1078 tests passed with the change applied temporarily, so nothing relies
on the redundant repaint.

### ~~2. Run the suite in parallel~~ — done, CI's runs still to watch

**Measured, all green three runs in a row:**

| Workers | Scheduling | Suite |
|---|---|---|
| 1 (today) | — | 15.5 s |
| 4 | `load` | 7.9 s |
| 8 | `load` | 6.2 s |
| 12 (`auto`) | `load` | 7.0 s |
| 8 | `worksteal` | **5.9 s** |
| 8 | `loadfile` | 7.3 s |

The floor is each worker's startup: about 0.9 s to import PySide6, numpy and
the package, plus about 1 s to collect. Twelve workers are no faster than
eight, because that fixed cost is paid twelve times. With step 1 applied the
parallel time barely moved (6.45 s), since parallel runs are bound by startup
rather than by per-test cost. The two steps help different situations:
step 1 the single test and the serial run, step 2 the whole suite.

Isolation already holds per process. `conftest.py`'s temporary home,
settings, cache directory and dialog guard are all session fixtures, and each
worker gets its own session. Three consecutive green runs are evidence that
no test depends on another's leftovers.

- [x] `pytest-xdist` added to the `dev` extra in `pyproject.toml`, and
      `uv.lock` updated. *The lock gained `pytest-xdist` 3.8.0 and `execnet`
      2.1.2 and nothing else moved.*
- [x] **Not in `addopts`.** A plain `pytest` stays serial, so running one test
      under a debugger stays simple. `08`'s *Checks* gains
      `pytest -n 8 --dist worksteal` as the way to run everything.
- [x] CI runs with `-n auto --dist worksteal`. Its runners have two to four
      cores, so expect a smaller gain there, measured on the first run.
- [x] The mutation sweeps described in [09-workflow.md](../09-workflow.md)
      run the whole suite per mutation in parallel. A sweep of eighteen
      mutations drops from about four minutes to under two.
- [ ] Three consecutive green parallel runs on each CI platform before this
      is ticked, since Windows and macOS start processes more slowly and
      schedule threads differently.

### ~~3. A fast lane, and a `gui` marker that can be trusted~~ — done

**Measured: `pytest -m "not gui"` runs 877 tests in 4.1 s** before;
**884 in 3.8–4.4 s** after landing.

That is the inner loop for anything in `core/` or `audio/`. It is only
trustworthy if every test that builds a `QApplication` or a widget carries the
`gui` marker. Today that holds because it has been done by hand.

- [x] A test that fails if any test module that imports `PySide6` has no
      `gui` mark, at module level or on each test that needs it. The rule is
      then enforced rather than remembered. *Landed as
      `tests/test_markers.py`, with "imports `PySide6`" read as "reaches
      Qt": a test reaches it if the test, or a helper, class or fixture it
      uses, names something imported from a package module that imports
      PySide6 when it is imported — directly or through another — or imports
      one itself. Its first run found two. `test_stylesheet_parses` builds a
      `QApplication` and shows a widget, so the fast lane has always run it;
      it is now marked. A flags test named `immersive.app` only to patch
      `run` out of it, and now patches it by name. The rule costs 0.1 s,
      nearly all of it parsing 17 000 lines of source.*
- [x] `08`'s *Checks* names the fast lane and says what it leaves out.
- [x] *Thirteen mutations, all killed: a mark dropped from a module, from one
      test, and from the stylesheet test; and ten against the detector — no
      transitive step, packages' `__init__` not run, annotations counted as
      uses, fixtures asked for by name ignored, local imports ignored,
      `conftest.py` ignored, `TYPE_CHECKING` followed, deferred imports
      followed, the module mark not read, and a module's autouse fixtures
      ignored.*

### 4. Gates instead of sleeps

The four sleeping tests stand in for slow workers with `time.sleep`. Replace
the sleep with a `threading.Event` the stand-in waits on and the test sets
once it has seen what it needed: that a timer ticked, or that the second
import was refused.

- [ ] No test in `test_import.py` or `test_loading.py` calls `time.sleep`.
- [ ] The N-3 test still fails if preparing is moved onto the UI thread. The
      mutation from M2 phase 6's sweep is re-run to prove it.

This is worth about 0.5 s. It is worth more as determinism: a gate cannot be
too short on a loaded CI runner, and a sleep can.

### 5. Trim the slowest tests without weakening them

- [ ] **The convex-hull property** (589 ms). Evaluate the 5 000 curves with
      numpy rather than one `value_at` call at a time, or keep the loop and
      spend the 5 000 samples where the hull is tight. The mutation this test
      was written to catch — a solver that reads the wrong keyframe — must
      still be caught; re-run it.
- [ ] **The backend load** (222 ms). `load_backend()` caches its answer for
      the process, since a missing PortAudio will not appear mid-session.
      This is the only change here that touches application behaviour, and
      it does so harmlessly.
- [ ] The thousand-edit test and the fresh-interpreter tests stay as they
      are: what makes them slow is what they test.

### 6. Narrow the per-test fixtures to the tests that need them

Two autouse fixtures run around *every* test: `_empty_config` empties
settings and the config directory, and `_no_window_outlives_its_test` frees
widgets. For the 877 headless tests that is about 1 ms each, **about 0.9 s**,
spent tidying things they never touch.

- [ ] Both apply only to tests marked `gui`, which step 3 makes safe to rely
      on. The session-scoped redirect of the home directory stays for
      everything: it is a guard against accidents, and accidents are not
      marked.
- [ ] Last, because it is the smallest saving and the only step that relaxes
      an isolation guarantee.

## What this adds up to

| | Serial | Parallel (8, `worksteal`) | Fast lane |
|---|---|---|---|
| Before this plan | 15.5 s | — | 4.1 s |
| After steps 1–2 | **11.3 s** *(measured)* | **5.3 s** *(measured)* | 4.1 s |
| After steps 1–6 | ~10.5 s *(estimated)* | ~5 s *(estimated)* | ~3 s *(estimated)* |

The largest single saving is already known: step 2 plus step 1 take the full
suite from 15.5 s to under 6 s, and nothing in either weakens a test.

## Keeping it fast

M3 to M6 will add many GUI tests. At today's 50 ms each, a thousand more
would add almost a minute to the serial run.

- [ ] CI prints `--durations=15`, so a new slow test is visible in every run
      rather than discovered months later.
- [ ] Each phase's Outcome records the suite's serial and parallel times, as
      the test count is recorded now. A jump is then attributable to a phase.
- [ ] Where a test needs one widget, it builds that widget, not a
      `MainWindow`. The waveform and notice-surface tests already do; the
      media pool's could, for everything except importing.

## Not in this plan, and why

| Tempting | Why not |
|---|---|
| One window shared by a module's tests | It is how the leak happened: state carried from one test into the next. Every test starting from nothing is why a failure here means something |
| Stubbing Qt out of the GUI tests | Real grabs found real bugs — M9's shifting status bar and clipped notice list, M2's squeezed pool thumbnails — that a stub would have hidden |
| Fewer mutations per sweep | A sweep is where most of this project's missing tests were found; making it cheaper is step 2's job, not making it smaller |
| Twelve workers because the machine has twelve | Measured slower than eight |
