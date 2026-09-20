# 01 — Requirements & Decisions

## Functional requirements

### Project
- F-1 Create, open, save, "save as" projects.
- F-2 A project is a single `.3dim` JSON file referencing audio by **relative**
  path. Audio is never copied or bundled.
- F-3 Missing media on load is reported, not fatal: the clip stays, greyed, and
  a relink dialog is offered.
- F-4 Full undo/redo across every edit, unlimited depth within a session.

### Media pool
- F-5 Import WAV, AIFF, FLAC, OGG, MP3 (whatever libsndfile + a fallback decoder
  cover).
- F-6 Files of any sample rate/bit depth are accepted and resampled to the
  project rate (48 kHz) on load.
- F-7 Folder tree in the explorer, with search/filter.
- F-8 Audition a sample from the pool without placing it (plays non-spatially).
- F-9 Waveform peaks are computed once per file and cached to disk.

### Timeline
- F-10 A **channel** is a track with a colour, a spatial position and automation.
  It holds many clips over time. All of its clips emit from that one moving point.
- F-11 Add, remove, rename, reorder, recolour channels.
- F-12 Per channel: gain, mute, solo.
- F-13 Drag a sample from the pool onto a channel to create a clip at the drop
  position (snapped).
- F-14 Clips can be moved, trimmed from either edge, split, duplicated, deleted.
  All non-destructive — the source file is never modified.
- F-15 Per clip: gain, fade-in, fade-out.
- F-16 Global BPM and time signature drive a grid. Snap divisions 1/1 → 1/32
  plus triplets, and "off".
- F-17 Snap targets both the grid and other clips' edges.
- F-18 Any channel can override the global snap setting, including disabling it.
- F-19 Ruler switchable between bars:beats and minutes:seconds.
- F-20 Transport: play, pause, stop, return-to-start, loop region.
- F-21 Waveforms drawn inside clips.

### Spatial
- F-22 Coordinates are metres, listener at the origin. Axes in
  [03-data-model.md](03-data-model.md).
- F-23 Every channel has a 3D position: left/right, front/back, **and height**.
- F-24 Two editable orthographic views — top (X/Y) and front (X/Z) — plus a
  third, read-only 3D view with a fixed camera.
- F-25 Dragging a channel's icon in either ortho view sets its position live,
  audible immediately during playback.
- F-26 Distance from the head attenuates the source.
- F-27 The HRTF dataset is selectable: bundled default, or any user `.sofa` file.

### Automation
- F-28 Automatable parameters: `pos.x`, `pos.y`, `pos.z`, `gain`.
- F-29 Keyframes support linear, ease (bezier handles) and hold interpolation.
- F-30 The right-hand panel is a self-contained curve editor with its own time
  axis, **scroll- and zoom-linked to the timeline** so the two never disagree.
- F-31 Keyframes belong to the channel at absolute timeline time. Moving a clip
  does not move them — unless Shift is held, which drags the automation with it.
- F-32 Dragging a source icon writes keyframes only when automation is
  explicitly **armed**. Unarmed, dragging edits the static position.

### Rendering
- F-33 Realtime binaural preview following the playhead.
- F-34 Offline render to 24-bit stereo WAV at project rate.
- F-35 Optional per-channel binaural stems in the same render pass.
- F-36 Render is deterministic and bit-identical across runs on the same
  machine and build. Cross-platform bit-identity is not promised (D-40).
- F-37 Render shows progress and can be cancelled.

### HRTF bypass
- F-38 Any channel can bypass HRTF processing entirely. Its audio is summed
  into the stereo bus unprocessed — no convolution, no ITD, no distance
  attenuation.
- F-39 A **bypassed stereo** source keeps its stereo image intact. This is the
  one exception to D-16, which downmixes stereo to a mono point.
- F-40 A **bypassed mono** source is centred, and positionable with a pan
  control using a constant-power law. On a bypassed stereo source the same
  control acts as balance.
- F-41 Bypass is a static per-channel switch and is **not** automatable. Pan
  is automatable.
- F-42 Toggling bypass never destroys data: position automation is retained
  while inactive and takes effect again when bypass is turned off.
- F-43 Bypassed channels are visually distinct in the channel header, the
  parameters pane, the spatial views and the keyframe editor.

## Non-functional requirements

- N-1 Preview must sustain **32 simultaneously moving sources** at 48 kHz with a
  512-frame buffer without dropouts on a mid-range laptop.
- N-2 No audio dropouts during normal UI interaction — dragging, scrolling,
  opening dialogs.
- N-3 UI stays responsive (no frozen window) during import and render.
- N-4 Project load for a 100-clip project under 3 seconds, warm peak cache.
- N-5 `core/` is importable and fully testable with no Qt and no audio device.
- N-6 Runs on Windows, macOS and Linux from one codebase.

## Decision log

Every one of these is reversible; they're recorded so we stop re-litigating them.
The questions behind them, with the answers as given, are archived in
[07-qa-archive.md](07-qa-archive.md).

| # | Decision | Rationale |
|---|---|---|
| D-1 | Python, not C++ | UI-heavy app; numpy gives C-speed DSP; export is offline so quality is never GIL-limited; the audio callback is a clean seam to port later. C++ only wins for plugin export, which is out of scope. |
| D-2 | PySide6 over PyQt6 | LGPL, no commercial licence question. |
| D-3 | Realtime preview in v1 | Offline-only would make the workflow unusable for designing motion. |
| D-4 | Full 3D including elevation | Chosen explicitly. Costs nothing in the engine; it's a UI problem, solved by D-5. |
| D-5 | Two ortho views + read-only 3D | Precise mouse placement; no 3D camera controls to build. The 3D view is for reading the scene at a glance and for video capture. |
| D-6 | Channel = track holding many clips | Matches DAW mental models; keeps the spatial scene readable at 40 clips. |
| D-7 | Keyframes pinned to timeline, Shift to couple | DAW-standard default, with an escape hatch for designed per-clip motion. |
| D-8 | Curve editor is self-contained, but axis-linked | Keeps the timeline uncluttered without losing alignment. |
| D-9 | Dry HRTF only | Reverb is a project of its own. |
| D-10 | Listener fixed at origin | Halves the automation surface; no real use case yet. |
| D-11 | Internal engine fixed at 48 kHz float32 | One rate everywhere removes an entire class of bugs. |
| D-12 | Non-destructive clip editing | Source files are sacred. |
| D-13 | Project references audio by relative path | Keeps projects small and diffable; bundling can be added as an export. |
| D-14 | Command-pattern undo from day one | Retrofitting undo is a rewrite. |
| D-15 | Splitters, not dockable panels | Matches the specified layout; far less state to persist and debug. |
| D-16 | Stereo sources downmix to a mono point | A stereo file has no single position. Width handling deferred. |
| D-17 | Media fully resident in RAM, no streaming | Samples are short. A 4-minute stereo song is ~90 MB float32 — acceptable. Streaming deferred behind a size threshold. |
| D-18 | No VST hosting, ever | This is the one thing that would have forced C++. Closing it keeps D-1 safe. |
| D-19 | Explorer's bottom pane is a context-sensitive parameters pane | Resolves the truncated line in the original spec; fits the position in the layout. Contents per selection in [04-ui-spec.md](04-ui-spec.md). |
| D-20 | No per-channel HRTF override | Cheap to build, but mixing HRTF sets inside one mix sounds inconsistent. Cut deliberately. |
| D-21 | Distance rolloff is `1/r^n`, `n` default 1.0, `r` clamped to 0.2 m | Physically-correct `1/r` is often too aggressive in practice; exposing the exponent lets it be softened by ear without touching code. |
| D-22 | No air absorption in v1 | Cheapest possible realism win, but out of v1 scope. Revisit after M5 if depth feels flat. |
| D-23 | Clip drops onto an occupied span trim the existing clip | Magnetic behaviour matches DAW expectation; a modifier rejects the drop instead. |
| D-24 | 3D view is screen-recording only; no video file export in v1 | Keeps `QPainter` isometric sufficient. A frame-accurate exporter would need an offscreen GL renderer — left as a seam, not built. |
| D-25 | No freehand motion-path drawing on the canvas in v1 | Positioning is by dragging icons and editing curves. Path *presets* stay on the later list. |
| D-26 | Single global BPM, no tempo map | A tempo map touches the grid, snapping, every bars:beats conversion and every stored keyframe time. Not worth it for v1. |
| D-27 | src-layout, installed with `pip install -e .` | Makes it impossible to import the package from the CWD, so tests exercise what actually ships and packaging bugs surface immediately rather than at release. |
| D-28 | Absolute imports everywhere, `ruff` `TID252` enforced | Makes the import graph machine-checkable (which is what enforces N-5), keeps modules movable, and makes consumers greppable. |
| D-29 | `__init__.py` files stay empty; no re-exports | Re-exports create duplicate names, invite cycles, and blur the import-graph test. Only the top level holds `__version__`. |
| D-30 | Package resources via `importlib.resources`, never `__file__` | `__file__` path-walking breaks under PyInstaller and zipimport — exactly where it is hardest to debug. Free at M0, expensive at M8. |
| D-31 | hatchling as the build backend | No `setup.py`, native src-layout, clean dynamic versioning, and it is `uv`'s default. |
| D-32 | Per-channel HRTF bypass | Some material must not be spatialised: an already-mixed stem or backing track, a reference mix, or sub-bass, which carries little directional information and is smeared by convolution. Distinct from D-20, which is about *choosing a different dataset* per channel — that is still cut. |
| D-33 | Bypass also disables distance attenuation and ITD | "Leave it as-is" has to mean untouched, or the switch is a half-measure that still needs explaining. Channel gain, mute/solo and clip fades still apply — those are mix controls, not spatialisation. |
| D-34 | Bypass is not automatable | Switching between a convolved and a dry signal mid-playback is a discontinuity that clicks. Anyone who wants the effect can crossfade two channels, which is what they actually mean. |
| D-35 | Bypassed channels gain a `pan` parameter, automatable | Without it a bypassed mono sample is stuck dead centre, which makes the feature much less useful than it should be. |
| D-36 | Bypassed channels leave the spatial canvases and appear in a strip | They have no meaningful position, so drawing them on the canvas is a lie; parking them all at the origin would pile them into an unreadable heap. |
| D-37 | Unconditional per-block input-windowed filter crossfade | Block-rate filter switching without a crossfade produces zipper noise on moving sources; the overlap-add tail does not cover the direct path, only the decay. Windowing the input keeps both halves full-length convolutions so their tails add correctly. Costs 2 extra iFFTs per block, constant in source count. |
| D-38 | `numpy>=2.0` is a hard requirement | `np.fft.rfft`/`irfft` only accept `out=` and stay in float32 from numpy 2.0. Below that the FFTs allocate a float64 array inside the audio callback every block, which breaks the zero-allocation rule outright. |
| D-39 | `sys.setswitchinterval(0.001)` at application startup | CPython's 5 ms default lets a UI paint hold the GIL for half the audio budget. One line in `app.py`, before the stream opens, bounds each wait to ~1 ms. |
| D-40 | Determinism is per machine and build, not cross-platform | FFT library versions and SIMD dispatch differ legitimately between platforms. Promising bit-identity across them would make F-36 a test we could only pass by weakening it. |
| D-41 | Stems render pre-limiter | The limiter is nonlinear and responds to the summed signal, so its gain reduction cannot be decomposed per stem. Stems that sum exactly are worth more than stems that match the delivered master sample-for-sample. |
| D-42 | Implicit 32-sample fade on clip edges away from media boundaries | A zero-length fade mid-waveform clicks, and split/trim produce such edges by definition. Exempting true file start and end keeps a full-length bypassed stem bit-transparent. |
