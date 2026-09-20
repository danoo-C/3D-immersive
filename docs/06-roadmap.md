# 06 — Roadmap

Nine milestones. Each ends at something you can actually run and judge, not at
an internal refactor.

This file stays at the milestone level and is the index of truth for milestone
status. The phase-by-phase breakdown of a milestone lives in its own directory
— `docs/m1_core_model/` and so on — created when that milestone starts. See
[09-workflow.md](09-workflow.md). The ordering is driven by one principle: **de-risk the
audio engine early**, because it is the only part that could invalidate the
choice of Python.

---

## M0 — Scaffolding ✅ *complete*
*Nothing audible.*

- `pyproject.toml` (hatchling), `uv` environment, pinned dependencies
- `pip install -e ".[dev]"`; absolute imports enforced by `ruff` `TID252`
- Package skeleton per [02-architecture.md](02-architecture.md)
- `ruff` + `mypy` + `pytest` configured, CI running them on Linux/macOS/Windows
- `theme.py` with the palette, and a main window with the three splitters and
  empty labelled panels

**Done when:** `python -m immersive` shows the dark, empty, correctly-proportioned shell.

**Delivered.** `pyproject.toml` (hatchling, src-layout, `TID252` banning
relative imports), the full package skeleton, `ruff` + `mypy` + `pytest`
configured and passing, GitHub Actions across Linux/macOS/Windows on 3.11 and
3.13, `theme.py` holding the palette, and a `MainWindow` with all seven regions
as labelled placeholders. 26 tests pass, including the import-graph test —
which carries its own test proving the detector is not passing vacuously while
`core/` is still empty.

---

## S0 — Listening spike (throwaway)
*Not a milestone. A script whose only job is to be listened to.*

Nothing in the plan puts a moving source in anyone's ears until M4, three
milestones away. That is a long time to be building on an unheard assumption,
and the two riskiest decisions in the whole design — the ITD/minimum-phase
split and the per-block crossfade — are decisions only listening can confirm.

So: one script, `spikes/binaural_spike.py`, **outside `src/`**. Not part of the
package, not imported by anything, excluded from the wheel. It needs no audio
device, so it runs here on WSL and writes WAV files to listen to on headphones.

**What it does**

- Load a full-sphere SOFA set (SADIE II D1 or ARI) and print its licence.
- Resample to 48 kHz, level-normalise.
- ITD extraction and minimum-phase split, per
  [05-audio-engine.md](05-audio-engine.md) §2.
- Triangulation and barycentric lookup, per §3.
- The per-block engine for **one** source at block 512, including the
  input-windowed crossfade (D-37) and the ITD buffer-length and sign
  constraints from *Prepare the bank*.

**What it produces** — four files, 8 s each, in `spikes/out/`:

| File | Content | What it proves |
|---|---|---|
| `orbit_noise.wav` | pink noise, 100 ms on/off bursts, orbiting 1 rev/s at ear level, 1.5 m | localisation is convincing at all |
| `orbit_tone.wav` | sustained 440 Hz sawtooth, same orbit | **the zipper test** — must be smooth |
| `orbit_tone_nocrossfade.wav` | same, crossfade disabled | the A/B that shows what D-37 buys |
| `front_back_clicks.wav` | click train sweeping front → overhead → behind | elevation and front/back work |

It also prints per-block processing time, mean and p99 — an early data point
for the M4 benchmark.

**Constraints:** under ~300 lines. numpy/scipy plus `sofar` and `soxr`, nothing
else. Not generalised, not tidied, not moved into `src/` afterwards. If it
turns out to be useful twice, it gets rewritten properly inside the package.

**Done when:** the four files exist, they have been listened to on headphones,
and a default SOFA set has been chosen. Feeds QA-30 and M4.

---

## M1 — Core model, headless
*No UI work at all.*

- Pin `numpy>=2.0` in `pyproject.toml` — a hard floor, not a preference
  (D-38); the realtime zero-allocation rule depends on it
- `model.py`, `curves.py`, `time.py` dataclasses
- Curve evaluation: linear, hold, ease with bezier solve
- Snapping and bars:beats ↔ samples conversion
- `commands.py` undo stack + first concrete edits
- `project_io.py` save/load with `schema_version` and a migration hook
- The import-graph test that forbids Qt, `sounddevice`, `immersive.ui` and
  `immersive.audio` inside `core/` (sketch in [02-architecture.md](02-architecture.md))

**Done when:** a project can be built in code, edited, undone, saved, reloaded
and compared equal — all in pytest, with no window open.

---

## M2 — Media
- Decode via `soundfile`, resample to 48 kHz via `soxr`, hold in RAM
- Content hashing, relink handling
- Peak pyramid generation + on-disk cache
- Media pool tree in the explorer, with filter and drag source
- Waveform widget, reused later by clips and the parameters pane
- Audition playback: the first use of `sounddevice`, deliberately trivial

**Done when:** you can import a folder, see waveforms, and double-click to hear
a sample.

---

## M3 — Timeline
- Channels: create, rename, reorder, recolour, gain/mute/solo, bypass flag
- `QGraphicsView` timeline with ruler, grid, playhead, loop region
- Drop from pool → clip; move, trim, split, duplicate, delete
- Snap with global setting, per-channel override, and `Alt` bypass
- Transport and keyboard shortcuts
- **Non-spatial** playback: scheduler + clip reads + gains → straight stereo

**Done when:** you can build an arrangement and hear it play back flat. This
validates the whole realtime plumbing — command ring, snapshot swap, xrun
counting — *before* any HRTF complexity is layered on top.

---

## M4 — Binaural engine 🔴 *the risk milestone*
- Pick and bundle the default full-sphere SOFA dataset (listening test; see
  QA-24 in [07-qa-archive.md](07-qa-archive.md))
- SOFA loading, resampling, normalisation
- ITD extraction + minimum-phase decomposition
- Spherical triangulation + barycentric interpolation + KD-tree lookup
- Frequency-domain bank, disk cache
- Batched FFT convolution with frequency-domain summation
- Distance attenuation with tunable rolloff (D-21), fractional-delay ITD with
  non-negative ramps and `nfft` sized for the dataset's maximum ITD
- The unconditional per-block input-windowed filter crossfade (D-37), with a
  named listening test: a sustained 440 Hz sawtooth orbiting at 1 rev/s must
  have **no buzz at the block rate**. Render the same pass with the crossfade
  disabled and A/B them — if the two are indistinguishable, the crossfade is
  not actually running
- `sys.setswitchinterval(0.001)` in `app.py` before the stream opens (D-39),
  measured with the xrun counter **while the UI is actively repainting** —
  an idle UI will show no difference and prove nothing
- The bypass path: stereo-preserving reads, pan law, summing after the iFFT
- Implicit 32-sample edge fades in the scheduler (D-42)
- The zero-allocation test on `process()`
- **A benchmark against N-1: 32 moving sources, 512 block, zero xruns**

**Done when:** positions set numerically in a test project are audibly, correctly
placed — and the benchmark passes. If it does not pass here, we find out now,
with the port seam still tiny, rather than after the UI is built on top.

---

## M5 — Spatial workspace
- Top (X/Y) and front (X/Z) ortho views: head glyph, rings, channel icons
- Drag to position, live during playback
- Motion trails and keyframe diamonds drawn from the curves
- Read-only isometric 3D view via `QPainter`
- Distance-as-radius, gain-as-opacity, mute/solo states
- The bypass strip under the top view, and bypassed channels leaving the canvases
- Position spinboxes in the parameters pane, two-way bound

**Done when:** you can drag a sound around the head while it plays and hear it
move.

---

## M6 — Automation
- Keyframe editor panel: axes, curves, diamonds, bezier handles
- Time axis locked to the timeline's scroll and zoom
- Insert, move, box-select, group drag, delete, interpolation menu
- Multi-curve overlay with per-parameter visibility
- The `ARM` toggle and write-on-drag behaviour
- Shift+drag clip coupling (D-7)
- Engine reads curves per block

**Done when:** you can animate a sample orbiting the listener and watch the
trail, the curve and the sound agree.

---

## M7 — Render
- Offline render reusing `Engine.process`, no device
- Render dialog: range, block size, stems toggle, output path
- Progress + cancel on a worker thread
- 24-bit WAV writing
- Per-channel stems, rendered **pre-limiter** (D-41). The render dialog says
  so on screen: *"stems are unlimited; they sum to the pre-limiter master"*
- An exactness test: stems sum sample-for-sample to a **pre-limiter** master
  render
- A determinism test: render twice **on the same machine and build**, assert
  bit-identical. Not asserted across platforms (D-40)

**Done when:** the exported file matches what the preview sounded like.

---

## M8 — Polish & ship
- Preferences: audio device, block size, HRTF set, theme details
- Session persistence: window geometry, splitters, recent projects
- Missing-media relink dialog
- Error surfaces: xrun indicator, load failures, clipping warning
- Empty states and a first-run sample project
- `PyInstaller` bundles for Windows, macOS and Linux
- README with install instructions per platform

**Done when:** someone who is not you can install it and make a mix.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Python realtime dropouts | Medium | M4 benchmarks it before anything is built on top; zero-alloc test; the `Engine.process` port seam is deliberately small |
| HRTF interpolation artifacts on moving sources | **High if done naively** | Two halves, both non-optional and both specified in [05-audio-engine.md](05-audio-engine.md): the ITD/minimum-phase split, which prevents comb filtering *within* a block's filter, and the unconditional input-windowed crossfade (D-37), which prevents zipper noise *between* blocks. Neither covers the other. S0 puts both in someone's ears before M1 rather than after M4 |
| Timeline repaint performance at hundreds of clips | Medium | `QGraphicsView` + cached pixmaps + zoom LOD from the start, not retrofitted |
| Cross-platform audio backend differences (WASAPI/CoreAudio/PipeWire) | Medium | Device picker with explicit backend choice; CI can't test audio, so manual smoke test per platform per milestone |
| macOS packaging and notarisation | Medium | Deferred entirely to M8; do not let it leak earlier |
| Curve editor and timeline time axes drifting apart | Medium | One shared `TimeAxis` object owns scroll and zoom; both widgets observe it, neither owns it |
| Scope creep into a general DAW | **High** | The "out of scope" table in [00-overview.md](00-overview.md) is the answer to every "could it also…" |

## Development environment note

You are on WSL2. WSLg audio works but latency is poor and device control is
limited, which makes it unsuitable for judging the preview or for the M4
benchmark. Recommended: edit wherever you like, but **run and test on Windows
native Python** (WASAPI, ideally ASIO) or a native Linux install. Treat WSL as a
place to run `pytest` on `core/`, which needs no audio device at all — that is
partly why N-5 exists.
