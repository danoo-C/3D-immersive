# 02 — Architecture

## Why Python, and where the exit is

The hard parts of this app are (a) a lot of bespoke UI — timeline, clip editing,
two spatial canvases, a curve editor — and (b) HRTF convolution.

Python loses on (a) nothing and wins on iteration speed. On (b) it loses
nothing either, because the convolution runs in numpy's FFT, which is C. What
Python genuinely risks is the *realtime* path: the GIL and GC can stall an audio
callback and cause dropouts.

Two things make that risk acceptable:

1. **The export is offline.** Final quality is never limited by scheduling. The
   preview only has to be good enough to audition, so a 512-frame buffer
   (~10.7 ms) is fine — nobody is playing an instrument through this.
2. **There is exactly one seam.** Everything realtime lives behind
   `audio.engine.Engine.process(block) -> (L, R)`. If Python ever fails N-1,
   that one function is reimplemented in C++/Rust/Cython and the entire UI is
   untouched. The reverse rescue — making a C++ project iterate quickly — does
   not exist.

## Layering

```
        ui/                 Qt. Knows about core. Never touches audio devices.
         │
         ▼
       core/                Pure Python. No Qt, no PortAudio. Fully testable.
         │                  Project model, curves, time, undo, project I/O.
         ▼
      audio/                numpy DSP + device I/O. Knows about core. No Qt.
```

The rule that matters: **`core/` imports neither Qt nor `sounddevice`.** That is
what makes N-5 true, and it is enforced by a test that walks the import graph.

`ui` and `audio` communicate only through `core` model objects and a command
queue — never by calling each other directly.

## Repository layout

The directories below exist as of M0. Modules listed inside them are planned
placements, created as their milestone lands — the packages are real, the
individual files are the map.

```
src/immersive/
  __main__.py            python -m immersive
  app.py                 wiring: build model, engine, window

  core/
    model.py             Project, Channel, Clip, MediaFile  (plain dataclasses)
    curves.py            Curve, Keyframe, interpolation, sampling
    time.py              samples ↔ seconds ↔ bars:beats, snapping
    commands.py          Command base + undo/redo stack
    edits.py             concrete commands (MoveClip, AddKeyframe, …)
    selection.py         what is currently selected, observed by ui
    signals.py           tiny observer so core can notify without Qt
    io/
      project_io.py      .3dim (de)serialisation + schema migration
      media.py           decode, resample to 48k, cache in RAM
      peaks.py           min/max peak pyramid, on-disk cache

  audio/
    engine.py            the realtime graph. THE SEAM.
    device.py            sounddevice stream lifecycle, device enumeration
    scheduler.py         timeline → which clips are active this block
    dsp.py               gain, fades, resampling, limiter
    render.py            offline render (reuses engine.process)
    hrtf/
      sofa.py            load SOFA → HRIR set, resample, normalise
      prepare.py         ITD extraction + minimum-phase decomposition
      interp.py          spherical triangulation + barycentric lookup
      bank.py            the ready-to-use frequency-domain HRTF bank

  ui/
    main_window.py       menus, toolbar, splitter layout
    theme.py             palette + qss
    explorer/            media pool tree (top) + params pane (bottom)
    timeline/            ruler, channel headers, clip lanes, playhead
    spatial/             ortho_view.py (top & front), view3d.py (read-only)
    keyframes/           curve editor panel
    widgets/             shared small widgets
  assets/
    hrtf/                bundled default SOFA set
    icons/
tests/
docs/
```

## Imports and packaging

### src-layout, installed editable

The package lives at `src/immersive/` and is installed into the venv with:

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

The `src/` directory is not decoration. Without it, the package sits at the
repository root and is importable *from the current working directory* — so
running `pytest` from the root imports the source tree directly and never
exercises the installed package. Packaging mistakes (a missing `__init__.py`,
package data that was not declared, a module left out of the wheel) then stay
invisible until release day. With `src/`, the only way to import `immersive` is
through the install, so what the tests exercise is what ships. → D-27

### Absolute imports only

```python
from immersive.core.model import Channel  # yes
from immersive.audio.hrtf.interp import barycentric

from ..core.model import Channel  # no
from .interp import barycentric  # no
```

Four reasons, in order of how much they matter here:

1. **The layering rule is machine-checkable.** `core/` must import neither Qt
   nor `sounddevice` (N-5), and that is verified by a test that parses the
   import graph. Absolute imports make every edge in that graph explicit and
   unambiguous; relative ones have to be resolved against each file's position
   first, which is both more code and more ways to be wrong.
2. **Moving a file cannot silently change meaning.** `from ..core import x`
   means something different after the module moves one level down. It usually
   still imports, just the wrong thing.
3. **Greppability.** `grep -rn "immersive.core.curves"` finds every consumer of
   a module. With relative imports that search is impossible, which makes
   "what breaks if I change this" unanswerable without an IDE.
4. PEP 8 recommends them, and every refactoring tool handles them better.

**Enforced, not merely agreed:**

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "TID", "RUF"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"
```

`TID252` makes a relative import a lint error. One rule, no judgment calls at
review time, no drift. → D-28

### `__init__.py` stays empty

Every package directory gets one, and it contains nothing — except the top
level, which holds `__version__` and nothing else.

Re-exporting from `__init__.py` (`from immersive.core.model import *`) creates
two names for every object, invites import cycles, and makes the import-graph
test ambiguous about what actually depends on what. Import from the module that
defines the thing. → D-29

The version lives in exactly one place and the build reads it:

```python
# src/immersive/__init__.py
__version__ = "0.1.0"
```
```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "src/immersive/__init__.py"
```

### The import-graph test

The thing that makes the layering in this document real rather than aspirational:

```python
# tests/test_layering.py
import ast
from pathlib import Path

CORE = Path(__file__).parent.parent / "src" / "immersive" / "core"
FORBIDDEN = ("PySide6", "sounddevice", "immersive.ui", "immersive.audio")


def _imported_names(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_core_imports_no_qt_no_audio_no_ui():
    offenders = []
    for path in CORE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _imported_names(tree):
            if name.startswith(FORBIDDEN):
                offenders.append(f"{path.relative_to(CORE.parent)}: {name}")
    assert not offenders, "core/ must stay pure:\n" + "\n".join(offenders)
```

It runs in CI on every commit and takes milliseconds. If someone reaches for a
`QColor` inside `core/model.py` because it is convenient, they find out
immediately rather than at the point where `core/` can no longer be tested
headless.

### Type-only imports

Where a type annotation would create a cycle, guard it rather than falling back
to a relative import:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from immersive.core.project import Project
```

The layering is acyclic by design (`ui → core ← audio`, and `core` imports
neither), so this should be rare. If it stops being rare, the layering has
drifted and that is the actual bug.

### Package resources

Bundled assets — the default HRTF dataset, icons — are read through
`importlib.resources`, never by walking up from `__file__`:

```python
from importlib.resources import files

sofa = files("immersive.assets.hrtf") / "default.sofa"
```

`Path(__file__).parent / "assets"` works in a checkout and breaks the moment
the app is a PyInstaller bundle or a zipimport, which is exactly when it is
hardest to debug. Getting this right at M0 costs nothing; retrofitting it at M8
costs an afternoon of confusing bug reports. → D-30

⚠️ **Packaging gotcha to remember:** hatchling excludes `.gitignore`d files from
builds, and `src/immersive/assets/hrtf/*.sofa` **is** gitignored (the datasets
are fetched, not committed — QA-30). Without an explicit override the shipped
wheel would silently contain no HRTF data:

```toml
[tool.hatch.build]
artifacts = ["src/immersive/assets/hrtf/*.sofa"]
```

### How this interacts with `launch.py`

`launch.py` puts `src/` on `PYTHONPATH` before handing off to the venv
interpreter. Once the editable install exists that is redundant — but it is
kept deliberately, because it means a fresh clone can be launched and diagnosed
*before* anything is installed.

There is no conflict between the two: a PEP 660 editable install resolves
`immersive` to the same `src/immersive/` directory that `PYTHONPATH` points at,
so both paths land on the same files. The only case where they could differ is
a *non-editable* install sitting in `site-packages`, and there `PYTHONPATH`
wins — which in a development checkout is the behaviour you want anyway.

### Build backend

**hatchling.** No `setup.py`, native src-layout support, clean dynamic
versioning, and it is `uv`'s default so the toolchain agrees with itself.
setuptools would also work; there is no reason to prefer it here. → D-31

## Threading

| Thread | Owns | Must never |
|---|---|---|
| **UI** (Qt main) | All widgets, the `Project` model, the undo stack | Block for more than a frame |
| **Audio** (PortAudio callback) | Engine state, preallocated buffers | Allocate, lock, log, or touch the model |
| **Workers** (`QThreadPool`) | Decode, resample, peak generation, offline render | Touch widgets directly |

### Crossing from UI to audio

The audio thread never reads the `Project` model. Instead:

- **Parameter changes** (position drag, gain, mute) go through a lock-free
  single-producer/single-consumer ring buffer of small fixed-size command
  structs. The callback drains it at the top of each block.
- **Structural changes** (add clip, load media) build a new immutable
  *engine snapshot* on the UI thread and hand it over with one atomic pointer
  swap. The old snapshot is freed on the UI thread, never in the callback.

### Keeping the callback honest

- All buffers preallocated at stream start; every numpy op uses `out=`.
- `gc.freeze()` after project load; GC runs explicitly on the UI thread.
- No `try`/logging/string formatting inside `process()`.
- An xrun counter is exposed in the UI so dropouts are visible, not mysterious.

## Signal flow per block

```
 drain command ring
 → for each channel: evaluate automation at block time
 → scheduler: gather active clips, read samples, apply clip gain + fades
 → per-channel gain, mute/solo
 → distance attenuation
 → HRTF: batched FFT convolution, summed in the frequency domain
 → 2 inverse FFTs → stereo bus
 → master gain → limiter → output
```

The frequency-domain summation is the important trick: because all sources are
summed *before* the inverse transform, the cost of the inverse FFT is constant
regardless of how many channels exist. See
[05-audio-engine.md](05-audio-engine.md).

## Undo

Every mutation of the model is a `Command` with `do()` / `undo()`, pushed onto a
stack. Nothing edits the model directly — not the UI, not project load. This is
why D-14 is day-one and not later: retrofitting it means rewriting every editing
path.

Continuous gestures (dragging a clip, dragging a source icon) push **one**
command on mouse-release, coalescing the intermediate states.

## Dependencies

| Package | For |
|---|---|
| `PySide6` | UI |
| `numpy>=2.0` | DSP, FFT. **The floor is hard:** `rfft`/`irfft` only accept `out=` and stay in float32 from 2.0, and without that the audio callback allocates every block (D-38). |
| `scipy` | spherical triangulation, optional faster FFT |
| `sounddevice` | PortAudio bindings |
| `soundfile` | libsndfile decode/encode |
| `soxr` | high-quality resampling |
| `sofar` | SOFA HRIR loading |
| `pytest`, `pytest-qt` | tests |
| `ruff`, `mypy` | lint, types |
| `pyinstaller` | packaging |

Pinned in `pyproject.toml`; `uv` for environment management.
