# 08 — Environment, Launching & Installation

## Current state

| Item | Status |
|---|---|
| `.venv/` | ✅ created, Python 3.13.12 |
| `launch.py` | ✅ working, with `--install` |
| `.gitignore` | ✅ written |
| `pyproject.toml` | ✅ hatchling, src-layout, ruff/mypy/pytest configured |
| `LICENSE` | ✅ MIT, declared and packaged; third-party notices beside it |
| Dependencies | ✅ installed; floors in `pyproject.toml`, exact versions in `uv.lock` |
| `src/immersive/` | ✅ M0 skeleton + themed shell |
| CI | ✅ `.github/workflows/ci.yml`, 3 platforms × 2 Python versions |
| `installer.py` | 📄 specified below, **not built** |

`python3 launch.py --check` reports exactly where you are at any time.

---

## Development environment

### Setup

One command, from a fresh clone, with any Python on the machine:

```bash
python3 launch.py --install --dev      # create venv, install everything
python3 launch.py --install --run      # ...and start the app straight after
```

That is equivalent to doing it by hand:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"     # once pyproject.toml exists (M0)
```

The `-e` matters: it is a src-layout package and absolute imports
(`from immersive.core.model import Channel`) resolve through the install, not
through the current working directory. See *Imports and packaging* in
[02-architecture.md](02-architecture.md) for why that is the rule.

On Windows the interpreter is `.venv\Scripts\python.exe`.

**On Linux, install PortAudio as well:** `sudo apt install libportaudio2` (or
your distribution's equivalent). `sounddevice`'s Windows and macOS wheels
bundle it; the Linux wheel does not, and without it `import sounddevice`
raises. The application still starts without it — audio output is simply
unavailable, and the window says so and names this package (M2 phase 7) —
but nothing can be heard. WSL counts as Linux here.

### Checks

```bash
.venv/bin/ruff check .           # lint, including the no-relative-imports rule
.venv/bin/ruff format --check .  # formatting
.venv/bin/mypy                   # types
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -n 8 --dist worksteal   # everything, in parallel
.venv/bin/pytest -m "not gui"    # the fast lane: nothing that needs Qt
```

**Run the whole suite in parallel.** Eight workers with work-stealing took
it from 11.3 s to under 6 s where it was measured. More workers than that was
slower, because each pays about two seconds to start. A plain `pytest` still
runs serially — deliberately not in `addopts` — so a single test under a
debugger behaves as it always has. CI runs `-n auto`, sized to the runner.

**The fast lane is for work in `core/` and `audio/`.** `-m "not gui"` runs
every test that needs no Qt — the model, curves, time and undo, both file
formats, decoding, hashing and peaks, the theme system, and audition against
its stand-in — in about four seconds, serially. It leaves out every test
marked `gui`: anything that builds a `QApplication`, a widget or a window,
which is the main window, the pool, the waveform, theme switching, the notice
surface and the real launches. That is a fifth of the tests and most of the
time, so run everything before trusting a change under `ui/`. The mark is
enforced rather than remembered: `tests/test_markers.py` fails any test that
reaches Qt without it, whether directly or through a helper, a fixture or an
import.

`QT_QPA_PLATFORM=offscreen` is set automatically by `tests/conftest.py`; it is
shown here because you will want it for any ad-hoc Qt script on a headless
machine, including WSL.

### Python version

**CPython 3.11 minimum, 3.13 in use.** Reasons for the floor: `tomllib` in the
stdlib, the `X | None` syntax used throughout, and improved error messages.

### Floors here, exact versions in the lock file

`pyproject.toml` declares **floors** — `numpy>=2.0` and the rest — because a
wheel that pins exact versions in its metadata is uninstallable alongside
anything else, and because the floors that matter have reasons attached
(`numpy>=2.0` is D-38, not a preference).

Reproducibility is a separate question, and it lives in a committed
`uv.lock`:

```bash
uv lock                 # regenerate after editing pyproject.toml
uv sync --extra dev     # recreate the environment exactly
```

The lock resolves for every supported platform and Python version, not just
the one that generated it, which is why it is `uv`'s and not `pip freeze`'s.
Recorded as D-67, because [06-roadmap.md](06-roadmap.md) listed "pinned
dependencies" as delivered at M0 while neither a pin nor a lock existed.

### Licence files

`LICENSE` is MIT and is declared with PEP 639's `license` / `license-files`
keys, so it ships inside the wheel — the older `license = { text = "MIT" }`
form put no licence in the distribution at all.

`THIRD-PARTY-NOTICES.md` ships beside it. It matters at M8 rather than now:
a PyInstaller bundle redistributes Qt, libsndfile and soxr, all LGPL, and
will redistribute an HRTF dataset under whatever licence M4 settles on
(QA-30). Those obligations are easy to meet and easy to forget at release
time, which is why the file exists before there is a bundle to attach it to.
`tests/test_docs.py` asserts it lists every runtime dependency.

### numpy version

**`numpy>=2.0` is a hard floor, not a preference** (D-38). The realtime
callback is required to allocate nothing, and that is only achievable because
`np.fft.rfft` and `np.fft.irfft` accept `out=` and operate on float32 without
upcasting — both of which arrived in numpy 2.0. On 1.x every block allocates a
fresh float64 array inside the audio callback. The pin belongs in
`pyproject.toml`; it is the first task of M1.

**Verified at M0:** PySide6 wheels exist for 3.11 and 3.13 on all three
targets — CI builds green on Linux, macOS and Windows across both. The
contingency this line used to carry, dropping the project to 3.12, is not
needed and nothing here would have required 3.13 anyway.

### You are on WSL2

`core/` tests run here happily; they need no audio device, which is exactly why
N-5 exists. The realtime preview and the M4 benchmark do **not** belong here —
WSLg audio has poor latency and limited device control. Run those on Windows
native Python (WASAPI, ideally ASIO) or a native Linux install.

From M3 on, `--device` and `--block` pick the output device and buffer size
without a preferences UI (F-55, D-63), which is what makes "run it on the
other machine to listen" a one-line change rather than a code edit:

```bash
python3 launch.py -- --device "Speakers (Realtek)" --block 512
python3 launch.py -- --device ?        # list what this machine offers
```

---

## `launch.py`

The one entry point. Runs under **any** Python on the machine, stdlib only, and
re-executes itself with the venv interpreter — so activation is never something
you have to remember.

```bash
python3 launch.py                    # start the app
python3 launch.py --check            # diagnose the environment, launch nothing
python3 launch.py --install          # create the venv and install everything
python3 launch.py --install --run    # install, then start the app
python3 launch.py --install --dev    # also install the dev tooling
python3 launch.py --help
python3 launch.py -- --verbose       # everything after -- is passed to the app
```

### What it does

1. Checks the bootstrap interpreter is ≥ 3.11.
2. Verifies `.venv` exists; if not, prints the exact command to create it.
3. Builds a child environment: `PYTHONPATH` gains `src/`, `VIRTUAL_ENV` is set,
   the venv's `bin`/`Scripts` goes first on `PATH`.
4. `os.execve`s the venv interpreter on POSIX — replacing the process rather
   than spawning a child, so Ctrl+C and exit codes behave normally. Windows
   uses `subprocess` instead, where `execv` handles signals badly.
5. Re-entering as the venv interpreter, it checks every runtime dependency and
   imports `immersive.__main__`.

Every failure mode prints what is wrong *and* the command that fixes it. Nothing
in it fails with a bare traceback.

### Why `PYTHONPATH` *as well as* an editable install

From M0 onward the package is installed with `pip install -e .` and absolute
imports work everywhere without any help. The `PYTHONPATH` injection is kept
anyway, so a fresh clone can be launched and diagnosed before anything is
installed. The two do not conflict — a PEP 660 editable install resolves
`immersive` to the same `src/immersive/` directory. Full reasoning in
[02-architecture.md](02-architecture.md) under *Imports and packaging*.

### `--install`

Creates `.venv` if it is absent, upgrades pip, then installs the project. With
a `pyproject.toml` present that is `pip install -e .` (plus the `dev` extra
when `--dev` is passed); before M0 adds one it falls back to installing the
runtime dependencies by name and says so.

pip output streams straight to the terminal rather than being captured — a
multi-minute install behind a silent spinner reads as a hang. Any failing step
aborts immediately; nothing is rolled back, and the message says to fix the
cause and re-run.

`--install --run` does both in one command. `--install` on its own finishes by
printing the environment report and how to start the app.

**It is behind a flag on purpose.** Installing automatically on every launch
means the first run hangs for minutes with no explanation, and every later run
pays a network check. Explicit is better: a plain `python3 launch.py` with a
broken environment tells you exactly what is missing and the one command that
fixes it.

### One source of truth for dependencies

Once the project is installed, the launch-time dependency check reads the
**installed distribution's own metadata** (`importlib.metadata`) rather than a
list inside `launch.py`. Add a dependency to `pyproject.toml` and the launcher
picks it up with no edit.

The `REQUIRED` list in `launch.py` is only the bootstrap fallback for a tree
that has not been installed yet, and it is labelled as such. Without this the
two lists would silently drift the first time a dependency is added.

`--check` runs that same check inside the venv by re-invoking this file with an
internal `--print-missing` flag, so both sides use identical logic instead of a
duplicated inline snippet.

---

## `installer.py` — specification only

**Not built. This section is the design, for review before any code exists.**

### Audience and purpose

For someone who wants to *use* the app and does not have a Python toolchain
mental model. It turns "clone a repo, make a venv, pip install, download an
HRTF set, make a shortcut" into a window with a Next button.

### Honest scope note

M8 already produces PyInstaller bundles, and for most end users on Windows and
macOS a bundle is a strictly better experience than any installer script. So
`installer.py` is **not** the primary distribution channel. It earns its place
in three specific cases:

- Linux, where there is no good single-bundle story
- Anyone who wants to modify the source afterwards
- Fetching the HRTF dataset, which is too large to embed in a bundle
  (see QA-30) and needs downloading regardless of how the app was installed

If those three stop being true, this file should be deleted rather than
maintained.

### Hard constraint: it cannot use Qt

The installer's job is to install PySide6, so it cannot itself depend on it.
GUI is therefore **tkinter**, which ships with CPython. That is not a stylistic
choice and should not be "improved" later.

Corollaries:
- Some Linux distributions package `tkinter` separately (`python3-tk`). The
  installer detects its absence and falls back to a console flow with the same
  steps, invoked explicitly as `python3 installer.py --console`.
- The installer is a **single file**, stdlib only, with no imports outside
  `os`, `sys`, `venv`, `subprocess`, `urllib`, `hashlib`, `json`, `pathlib`,
  `threading` and `tkinter`. It must run from a bare download.

### Screen flow

```
  1  Welcome          what this installs, disk space, licence
  2  Python check     found interpreter, version, verdict
                      ↳ fail: explain and link to python.org, stop here
  3  Location         default per platform, editable, "Browse…"
                        Windows  %LOCALAPPDATA%\3dImmersive
                        macOS    ~/Applications/3dImmersive
                        Linux    ~/.local/share/3dimmersive
  4  Options          ☑ desktop shortcut   ☑ start-menu entry
                      ☑ download HRTF dataset  (≈N MB)
                      ☐ install dev tools
  5  Install          progress bar, live log pane, Cancel
  6  Done             ▶ Launch now   📂 Open folder   Close
```

### Install steps, in order

| # | Step | Failure handling |
|---|---|---|
| 1 | Create the target directory | Permission error → offer a different location |
| 2 | Copy or extract the application source | Disk full → roll back |
| 3 | `python -m venv` into `<target>/.venv` | `ensurepip` missing → tell the user to install `python3-venv` |
| 4 | Upgrade pip | Non-fatal, log and continue |
| 5 | `pip install -r requirements.txt`, streaming output to the log pane | Network failure → retry button, and offer an offline wheel directory |
| 6 | Download the HRTF dataset, verify SHA-256, unpack to `assets/hrtf/` | Checksum mismatch → delete and retry once, then fail loudly |
| 7 | Write shortcuts | Non-fatal, log and continue |
| 8 | Smoke test: run `launch.py --check` in the target | Any failure → show the report verbatim, do not claim success |

Step 8 matters. An installer that reports success without verifying the result
is worse than one that fails honestly.

### Shortcuts per platform

| Platform | Mechanism |
|---|---|
| Windows | `.lnk` via a small PowerShell `WScript.Shell` call — avoids a `pywin32` dependency |
| macOS | a minimal `.app` wrapper whose `Contents/MacOS` script execs `launch.py` |
| Linux | a `.desktop` file in `~/.local/share/applications` plus an icon in `~/.local/share/icons` |

Each shortcut runs `<target>/.venv/bin/python <target>/launch.py`, so the
launcher stays the single entry point for every path into the app.

### Uninstall

`installer.py --uninstall` reads the manifest written at install time and
removes what it created, nothing else. It never recursively deletes a
user-chosen directory — it deletes the paths it recorded. **User projects and
rendered audio are never touched**, and it says so on screen.

### Manifest

`<target>/install-manifest.json` records version, install date, target path,
Python used, every path created, dataset id and checksum, and shortcut paths.
It is what makes uninstall and repair safe rather than guesswork.

### Threading

All work runs on a worker thread; tkinter is touched only from the main thread
via `after()`. A blocked UI during a five-minute pip install reads as a crash
and people force-quit halfway through.

### Testing

`--dry-run` walks every step and logs what it *would* do, touching nothing. CI
runs it on all three platforms; the real install path is smoke-tested on each
at release time only.

---

## On PyPy — and what to use instead

Short answer: **no, and there is a hard blocker before you even reach the
performance argument.** But the question is a good one, because the reasoning
points at what *would* help.

### The blocker

**PySide6 does not support PyPy.** Qt's Python bindings go through shiboken,
which is deeply tied to the CPython C-API. There is no PyPy build. The entire
UI layer — which is most of this application — simply will not import.

That ends it on its own. Everything below is why it would also not have helped.

### Why PyPy would not speed up the part you care about

PyPy wins by JIT-compiling **hot pure-Python loops**. This project has
essentially none, by deliberate design. Look at the hot path in
[05-audio-engine.md](05-audio-engine.md): a batched `rfft`, an array gather, a
complex multiply-accumulate, two `irfft`s. Every one of those is already C
running at full speed inside numpy. There is no interpreted loop for a JIT to
bite on.

Worse, numpy on PyPy runs through `cpyext`, PyPy's CPython-C-API emulation
layer, which adds overhead at every boundary crossing. For code like ours —
short Python, heavy C — PyPy is frequently **slower** than CPython. You would
be paying a compatibility tax on the exact calls that dominate the profile.

### And it is actively wrong for realtime audio

Two properties that are virtues elsewhere are liabilities in an audio callback:

- **JIT warmup.** Code is compiled *while running*, so the first seconds of
  execution have unpredictable pauses. Our callback has a 10.7 ms budget and a
  hard deadline. Unpredictable is worse than slow.
- **A moving, generational GC.** CPython's refcounting is unglamorous but
  predictable, and our strategy — preallocate everything, `gc.freeze()` after
  load, collect only on the UI thread — depends on that predictability. PyPy's
  GC does not offer the same control surface.

### What actually helps, in the order I would reach for it

If M4's benchmark (32 moving sources, 512-frame block, zero xruns) comes up
short, this is the escalation ladder:

| # | Lever | Expected gain | Cost |
|---|---|---|---|
| 0 | **`sys.setswitchinterval(0.001)`** at startup | Bounds each GIL wait to ~1 ms instead of 5 | One line (D-39) |
| 1 | **`scipy.fft` with `workers=`, or pyFFTW with a saved plan** | Often meaningful for repeated same-size transforms — FFTW plans once for our fixed `nfft` and reuses it forever | A dependency, a few lines |
| 2 | **Raise the block size** 512 → 1024 | Halves per-block Python overhead | +10 ms latency, still fine for auditioning |
| 3 | **Profile and kill remaining per-block allocations** | The zero-alloc test should already prevent these | Free |
| 4 | **Cython / nanobind on `Engine.process`** | Removes Python from the callback entirely | A few hundred lines, a build step — the documented seam in [02-architecture.md](02-architecture.md) |

**Row 0 deserves more than a table cell.** CPython releases the GIL every
5 ms by default. A Python-side paint event on the UI thread can therefore make
the audio callback wait up to 5 ms for the GIL — half of a 10.7 ms budget,
spent doing nothing. Dropping the switch interval to 1 ms bounds that wait to
roughly a fifth of what it was, at the price of slightly more thread-switch
overhead on the UI thread, which has milliseconds to spare and does not care.

It is one line in `app.py`, before the audio stream opens. It is also the only
row on this ladder that addresses the *actual* failure mode identified below —
contention, not throughput — which is why it sits at 0 rather than being
buried at the bottom. Its effect is not assumed: the M4 benchmark measures the
xrun counter with and without it **while the UI is actively repainting**,
because an idle UI will show no difference and prove nothing.

Note that #1 touches four lines, while the nuclear option at #4 is still
bounded and pre-planned. That ladder is why choosing Python was safe.

### The thing genuinely worth watching

**Free-threaded CPython** (the `3.13t` / `3.14t` no-GIL builds). Our actual
realtime risk is not raw speed — the margin there is large — it is the audio
callback contending with the UI thread for the GIL. Removing the GIL addresses
that directly, which is more relevant to this project than any JIT.

It is not adoptable yet: free-threaded wheels for numpy, scipy and especially
PySide6 are still maturing, and the free-threaded build is itself slower
single-threaded. Revisit at M8, and again a year after. Do not build on it now.

### Verdict

Stay on CPython 3.13 (3.12 if a PySide6 wheel forces it). PyPy is blocked by
PySide6, would not help the FFT-bound hot path, and is the wrong GC and warmup
profile for a realtime callback. The performance headroom we need comes from
the frequency-domain summation already in the design, and the fallbacks above
if that is not enough.
