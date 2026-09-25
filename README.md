> [!WARNING]
> **UNDER CONSTRUCTION**
>
> This project is in early, active development and is **not ready for use**.
> The application launches and some parts work, but you can't make a 3D mix
> with it yet. Expect missing features, breaking changes and a `.3dim` file
> format that may still change. See [Project status](#project-status) for
> what works today.

# Immersive

**A graphical 3D sound creator.** Arrange audio samples on a timeline, place
each channel in space around the listener's head, animate those positions with
keyframes, and render the result as a binaural stereo file. On headphones,
each sound comes from a specific point around you.

![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/UI-PySide6%20%2F%20Qt%206-41CD52?logo=qt&logoColor=white)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-under%20construction-orange)

---

## Contents

- [What it is](#what-it-is)
- [The core loop](#the-core-loop)
- [Planned for v1](#planned-for-v1)
- [Project status](#project-status)
- [How the 3D sound works](#how-the-3d-sound-works)
- [Getting started](#getting-started)
- [Development](#development)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [License](#license)
- [The original brief](#the-original-brief)

---

## What it is

A desktop application for composing music and sound design **in 3D space**.
You arrange samples on a timeline the way you would in any DAW, but each
channel also has a *position around the listener's head*, and you can animate
that position with keyframes. The output is binaural: an ordinary stereo WAV
that places every sound at a specific point in space when you listen on
headphones.

It is deliberately **not** a general-purpose DAW. It has no mixing console, no
plugin hosting, no MIDI and no recording. What it does that DAWs do badly is
treat spatial placement as a first-class property that you can see, edit and
animate.

**Who it's for:** producers and sound designers making headphone-first
material, such as binaural mixes, ASMR, spatial ambiences, game and film
pre-visualisation, and music that moves around you.

## The core loop

1. Create a project and import audio into the media pool.
2. Drag a sample onto a timeline channel. Each channel has its own colour.
3. An icon in that colour appears around the head in the spatial workspace.
4. Drag the icon to place the sound. Add keyframes to make it move.
5. Set the BPM and snap, and trim clips so they line up.
6. Render to a binaural stereo WAV.


## Planned for v1

- **Media pool:** import WAV, AIFF, FLAC, OGG and MP3 at any sample rate, with
  a folder tree, filtering, waveform previews and audition.
- **Timeline:** multiple channels with colour, gain, mute and solo. Clips can
  be moved, trimmed, split, duplicated, cut, copied and pasted, and every edit
  is non-destructive.
- **Grid and snap:** a global BPM and time signature, snap divisions from 1/1
  to 1/32 plus triplets, snapping to other clips' edges, and a per-channel snap
  override.
- **Full 3D positioning:** azimuth, elevation and distance, edited in two
  orthographic views (top X/Y and front X/Z) plus a read-only 3D view.
- **Automation:** keyframes on position and gain with linear, ease (bezier)
  and hold interpolation, in a curve editor whose scroll and zoom are locked
  to the timeline.
- **Per-channel HRTF bypass** for stems and material that must stay exactly
  as authored.
- **Realtime binaural preview** that follows the playhead.
- **Offline render** to a 24-bit stereo WAV, with optional per-channel stems.
  Renders are bit-identical from run to run on the same machine.
- **Project files and undo:** a single human-readable `.3dim` JSON file per
  project, and unlimited undo/redo.
- **Themes:** swappable `.3dimtheme` colour themes that switch without a
  restart.

**Out of scope for v1:** reverb and room simulation, a moving listener, head
tracking, VST hosting, MIDI and recording, time-stretch and pitch-shift,
ambisonic output, and tempo changes. The full list, with the reason for each
exclusion, is in [`docs/00-overview.md`](docs/00-overview.md).

## Project status

The work is split into milestones, and each one ends with something you can
run and judge. They are listed here **in build order**. The numbers are
identifiers, not positions: M9 is built third.

| Milestone | Delivers | Status |
|---|---|---|
| **M0** Scaffolding | Packaging, tooling, themed application shell | ✅ Complete |
| **S0** Listening spike | Throwaway script that tests the HRTF approach by ear | ✅ Complete |
| **M1** Core model | Headless project model, curves, time and snapping, undo, `.3dim` files | ✅ Complete |
| **M9** Theming | `.3dimtheme` format, live theme switching, notice centre | ✅ Complete |
| **M2** Media | Import, decode and resample, waveform cache, media pool, audition | 🟡 Built. Audition is waiting for a listening test on real hardware |
| **M3** Timeline | Channels, clips, editing, snapping, transport, flat (non-spatial) playback | 🚧 In progress |
| **M4** Binaural engine | Realtime HRTF rendering, benchmarked at 32 moving sources | ⏳ Not started |
| **M5** Spatial workspace | Drag sources around the head while you listen | ⏳ Not started |
| **M6** Automation | Keyframes and the curve editor | ⏳ Not started |
| **M7** Render | Offline binaural WAV and stems | ⏳ Not started |
| **M8** Polish & ship | Bundles, autosave and crash recovery, preferences. Beta is declared partway through | ⏳ Not started |

**What works today:** the application opens into its full window layout. You
can create, open and save projects with undo and redo, import a folder of
samples, browse them with waveforms in the media pool, audition them
(non-spatially), switch themes, and add, rename, recolour and reorder channels
on the timeline. Placing clips on the timeline is being built now.

**What doesn't work yet:** playing back an arrangement, any spatial or
binaural processing inside the app, keyframes, and rendering.

This table is a snapshot. The authoritative status of each milestone is kept
in [`docs/06-roadmap.md`](docs/06-roadmap.md).

## How the 3D sound works

Each channel is a single point source, and the listener's head stays fixed at
the origin. Sound is placed using **HRTFs** (head-related transfer functions)
loaded from standard [SOFA](https://www.sofaconventions.org/) datasets. These
are measurements of how sound from each direction reaches each ear.

Moving sources are where naive HRTF rendering falls apart, so the engine
uses two techniques:

- **The time delay and the spectrum are interpolated separately.** Each
  measured response is split once, at load time, into a broadband inter-aural
  time delay and a minimum-phase filter. Both are interpolated between
  directions on a triangulated sphere. Blending raw responses instead causes
  comb filtering, which makes a moving source sound flanged.
- **Every audio block crossfades between filters** (D-37). Without the
  crossfade, a source moving fast enough to change filters on each block
  produces zipper noise.

Both techniques were tested by ear before any application code relied on them.
In the S0 listening spike, the version without the crossfade was described as
*"horrible, like a dial up tone under the sound"*. The crossfaded version
sounded clean. Details are in
[`docs/s0_listening_spike/`](docs/s0_listening_spike/README.md) and
[`docs/05-audio-engine.md`](docs/05-audio-engine.md).

Performance target: **32 simultaneously moving sources** at 48 kHz with a
512-frame buffer and no dropouts on a mid-range laptop (N-1). All realtime work
sits behind one small function, `Engine.process`. If Python can't meet the
target, that one function can be rewritten in native code without touching the
rest of the application.

### Hear it today

The spike renders demo files you can listen to on headphones. It needs no
audio device:

```bash
.venv/bin/python spikes/binaural_spike.py --render   # writes WAVs to spikes/out/
```

On its first run it downloads the SADIE II D1 (KEMAR) HRTF dataset from
sofacoustics.org and verifies it against a checksum.

## Getting started

> These steps are for developers. End-user installers and bundles come at
> milestone M8.

### Requirements

- **Python 3.11 or newer** (3.13 is the version in use)
- **Git**
- **Linux only:** PortAudio, for example `sudo apt install libportaudio2`. The
  sounddevice wheels for Windows and macOS include it. Without it the app still
  starts, but it can't produce any sound.

### Install and run

`launch.py` is the single entry point. It runs under any Python on your
machine, builds the virtual environment for you, and re-launches itself
inside it, so you never need to activate anything.

```bash
git clone https://github.com/danoo-C/3d_imersive.git
cd 3D-immersive-main

python3 launch.py --install --run    # create .venv, install, start the app
```

After that:

```bash
python3 launch.py                    # start the app
python3 launch.py --check            # diagnose the environment without launching
python3 launch.py --install --dev    # also install the development tools
python3 launch.py --help
```

Anything after `--` goes to the application itself. For example, to choose
the audio output device and block size:

```bash
python3 launch.py -- --device ?                          # list available devices
python3 launch.py -- --device "Speakers (Realtek)" --block 512
```

Every failure message says what is wrong and gives the command that fixes it.
The full reference is [`docs/08-environment.md`](docs/08-environment.md).

## Development

```bash
python3 launch.py --install --dev                  # or: uv sync --extra dev

.venv/bin/ruff check .                             # lint
.venv/bin/ruff format --check .                    # formatting
.venv/bin/mypy                                     # type checking
.venv/bin/pytest -n 8 --dist worksteal             # full suite, in parallel
.venv/bin/pytest -m "not gui"                      # fast lane: no Qt needed
```

- **Dependencies:** `pyproject.toml` sets minimum versions, and the committed
  `uv.lock` pins exact versions for reproducible environments.
- **The fast lane** skips every test that needs Qt. It covers the model, file
  formats, decoding, peaks and the theme system in a few seconds, so use it
  while working in `core/` or `audio/`. Run the full suite before you trust a
  change under `ui/`.
- **Headless:** the test suite sets `QT_QPA_PLATFORM=offscreen` itself, so it
  runs on CI and WSL without a display.
- **Audio can't be tested automatically.** Realtime preview and the engine
  benchmark are checked by hand, on native Windows or Linux. WSL is fine for
  development and tests, but its audio latency is too poor to judge playback.

### How the work is organised

The project is specification-first. Before code is written, each milestone
in the [roadmap](docs/06-roadmap.md) is split into **phases**, which set what
must be true when the work is done, and **plans**, which set how it gets
done. Every requirement (`F-`, `N-`) and decision (`D-`) has a permanent
identifier in [`docs/01-requirements.md`](docs/01-requirements.md), and the
reasoning behind each one is recorded so that settled decisions aren't
re-argued. The rules are in [`docs/09-workflow.md`](docs/09-workflow.md) and
[`docs/doc-system.md`](docs/doc-system.md).

## Architecture

```
        ui/                 Qt. Knows about core. Never touches audio devices.
         │
         ▼
       core/                Pure Python. No Qt, no PortAudio. Fully testable.
         │                  Project model, curves, time, undo, project I/O.
         ▼
      audio/                numpy DSP + device I/O. Knows about core. No Qt.
```

- **`core/` imports neither Qt nor `sounddevice`**, so the entire model can be
  tested with no window and no audio device. A test that walks the import graph
  enforces this.
- `ui/` and `audio/` never call each other directly. They communicate only
  through `core` model objects and a command queue.
- The package uses a src layout (`src/immersive/`) with absolute imports only.
  `spikes/` holds throwaway experiments that the package never imports and
  never ships.

| | |
|---|---|
| Language | Python 3.11+ |
| UI | PySide6 (Qt 6) |
| DSP | numpy (2.0+) and scipy |
| Audio I/O | sounddevice (PortAudio) |
| File I/O | soundfile (libsndfile), soxr for resampling |
| HRTF | SOFA datasets via `sofar` |
| Tooling | hatchling, uv, ruff, mypy, pytest (+ pytest-qt, pytest-xdist) |

The full design is in [`docs/02-architecture.md`](docs/02-architecture.md).

## Documentation

The specification lives in [`docs/`](docs/). Start with the
[index](docs/README.md).

| Document | Covers |
|---|---|
| [00 — Overview](docs/00-overview.md) | What the app is, the stack, what's in and out of scope |
| [01 — Requirements & Decisions](docs/01-requirements.md) | Numbered requirements and the decision log |
| [02 — Architecture](docs/02-architecture.md) | Layering, repo layout, threading, the port seam |
| [03 — Data Model](docs/03-data-model.md) | Coordinates, time, entities, the `.3dim` file format |
| [04 — UI Specification](docs/04-ui-spec.md) | Layout, palette, every panel and interaction |
| [05 — Audio Engine](docs/05-audio-engine.md) | HRTF pipeline, the per-block hot path, realtime safety |
| [06 — Roadmap](docs/06-roadmap.md) | Milestones, build order, the risk register |
| [07 — QA Archive](docs/07-qa-archive.md) | Every design question asked, and the answer given |
| [08 — Environment](docs/08-environment.md) | The venv, `launch.py`, and the installer spec |
| [09 — Workflow](docs/09-workflow.md) | How milestones are broken into phases and plans |

**Suggested reading order:** 00 → 01 → 06 to get oriented, 08 to set up, and
02 → 03 before you implement anything.

## License

[MIT](LICENSE) © 2026 Daniel Danko.

The app depends on third-party components, several of them LGPL (Qt via
PySide6, libsndfile and soxr), and redistributes them when bundled. Their
licences and obligations are listed in
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

---

## The original brief

The project started from the hand-written spec below. It is kept word for word
as the record of what was originally wanted; only the heading levels have been
lowered to fit this page. Where it disagrees with [`docs/`](docs/), the
documents win.

<details>
<summary>Show the original brief</summary>

#### a GRAPHICAL 3d sound creator
##### how to use
- create a new project. add in sound files, anything, full songs or samples.
- select a sound file and drag it to the timeline. it will appear in the chanels color from the timeline (timeline has the chanels).
- click the channel and an icon the the chanels color appears around a head from the top wiew.
- you can move the icon around and it will project the sound in 3d space. (only works on headphones)
- do this for all samples and you have a full 3d mix of samples.
- optionally select the bpm of the song and the snap mode for easier sample alignment.
- also crop, cut the samples for them to align better.
- optinally disable snap mode on indiviadual chanels disregarding the global snap mode.
- and support for keyframes, so you can animate each chanel. basically you can assign keyframes to multiple chanels.


##### how the app looks
- its look is minimalistic and the colors are dark with a spice of purple. 
- a resisable timeline part on the bottom of the window.
- a list of sample in an explorer on the left above the timelibe.
- the rest is the main workspace occupying the middle of the window. 
- and the right side of the window above the timeline is the keyframe explorer.
- a top menu bar.

##### how the explorer looks
- explorer is spit into 2 parts, the main part on the top and middle, and the bottom part
- the bottom part is a resisable config/param

</details>

**Decided since the brief was written:** Python (PySide6 + numpy +
sounddevice), cross-platform, realtime binaural preview, and full 3D including
elevation. A channel is a track that holds many clips. Keyframes are pinned to
timeline time, and Shift+drag brings them along with a clip. The reasons for
each are in [`docs/01-requirements.md`](docs/01-requirements.md).

Two points in the brief have since been **overruled**:

- *"dark with a spice of purple"*: the surfaces are now VS Code's neutral
  greys and only the accent is still purple. The purple-black original looked
  like a toy, and a purple playhead is easier to see on grey than on
  purple-black (D-44).
- *"the rest is the main workspace occupying the middle"*: the workspace is
  two editable orthographic views (top X/Y and front X/Z) plus a read-only 3D
  view, arranged as **two tabs** rather than side by side. With three panes,
  each got a third of the width, which was too narrow to place a source
  precisely, and one of those thirds went to a view you can't drag in at all
  (D-5, D-49).

⚠️ The "how the explorer looks" section of the brief is **cut off
mid-sentence**. The missing text was never recovered, so the pane has been
specified as a selection-driven parameters pane. That is a reconstruction,
not a transcription. See [`docs/07-qa-archive.md`](docs/07-qa-archive.md),
QA-29.
