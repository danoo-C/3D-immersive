# 01 — Requirements & Decisions

## Functional requirements

### Project
- F-1 Create, open, save, "save as" projects.
- F-2 A project is a single `.3dim` JSON file referencing audio by **relative**
  path. Audio is never copied or bundled.
- F-3 Missing media on load is reported, not fatal: the clip stays, greyed, and
  a relink dialog is offered.
- F-4 Full undo/redo across every edit, unlimited depth within a session.
- F-49 A recovery copy of the open project is written periodically while it has
  unsaved changes, and offered on the next launch after an unclean exit. It is
  a sidecar file; the project itself is never written without being asked
  (D-64).

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
- F-50 Clips can be cut, copied and pasted, within a channel and between
  channels. Paste lands at the playhead on the selected channel.
- F-51 More than one clip can be selected at once, including across channels,
  by shift-click, ctrl-click and a rubber band over empty lane space. Every
  edit that takes a selection takes all of it.
- F-52 The transport shows the playhead position numerically, in the ruler's
  current unit.

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
- F-53 The render range is selectable: the whole project, the loop region, or a
  typed range. The default is the whole project (D-53).

### Output and monitoring

- F-54 A master output meter, with peak hold and a clipping indicator, is
  visible without opening anything. Per-channel meters are deliberately not
  provided (D-55).
- F-55 The audio output device and the block size are selectable, and the
  choice persists. Until the preferences UI exists they are settable from the
  command line (D-63).
- F-56 Anything the application needs to report — missing media, a malformed
  theme, a failed decode, a device that would not open — is visible in the UI
  and reviewable after the moment it happened. Never only on stderr (D-65).

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

### Theming
- F-44 Every colour the application draws comes from a **theme**, not from a
  literal value in a widget. The token vocabulary is in
  [04-ui-spec.md](04-ui-spec.md).
- F-45 A theme is a `.3dimtheme` file: JSON, versioned, human-editable.
- F-46 A theme file may be **partial**. Anything it omits falls back to the
  built-in default, so a two-line theme that changes only the accent is valid
  and stays valid when the application adds tokens.
- F-47 A theme that is missing, malformed or contains invalid colours is
  reported and the application starts on the default. A theme file can never
  prevent the app from running.
- F-48 Themes in the user's theme directory are discovered and can be selected
  and applied without restarting.

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
| D-43 | `ruff format` does not format Markdown (`[tool.ruff.format] exclude`) | Since ruff 0.13 the formatter rewrites Python blocks inside `.md`. The listings in `docs/` are spec pseudocode — `05`'s per-block engine calls methods that do not exist yet — so formatting them is a category error, and it had already turned CI's format step red. Linting still covers `docs/`; only formatting is opted out. |
| D-44 | Surfaces are VS Code's dark greys; the accent stays purple | The original purple-black surfaces read as a toy. Neutral greys are what the people who will use this already stare at all day, and a purple playhead is more visible on grey than on purple-black. The cost is real and is paid in `04`: against lighter greys `accent` no longer clears 4.5:1, so it is specified as a fill and stroke colour with `accent-glow` as the text-safe purple, and `error` moved to VS Code's error-text red. `tests/test_theme.py` asserts the ratios. |
| D-45 | A theme is a versioned JSON `.3dimtheme` file, merged over the built-in default | JSON because it is diffable, hand-editable and already the project format's language. Merged rather than replacing, so a partial theme is valid and — the part that matters — a theme written today keeps working when a later milestone adds tokens for widgets that did not exist yet. A replace-everything theme would break on every release. |
| D-46 | Two layers: `tokens` (named colours) and `groups` (per-widget roles) | One flat list of every colour in the app would be hundreds of entries and unusable by hand; one list of eight tokens could not express "this one button is different". Tokens give a coherent theme from a handful of edits; groups give fine control, and reference tokens by name so the coherence survives. |
| D-47 | The built-in theme ships as a `.3dimtheme` and loads through the same path as a user's | Dogfooding the format is the only way to know it can express what the app actually needs. A format that cannot describe the default theme is already broken, and without this the discovery is a bug report from a user rather than a failing test. |
| D-48 | A theme never blocks startup: unknown keys are ignored, bad values fall back, everything is reported | Strict parsing of a cosmetic file means a typo in a colour locks someone out of their own project. Lenient parsing with a visible report gets the same information to the author without that. This is the same instinct as F-3's non-fatal missing media. |
| D-49 | The workspace is two tabs — *Top / Front* and *3D* — not three side-by-side views | Three views each took about a third of the workspace, which at 1500 px is too narrow to drag a source precisely in, and one of those thirds went to a view that cannot be dragged in at all. The two editable ortho views stay together because placing a source is one gesture across both: X/Y, then height. The read-only 3D view is for reading the scene, so it does not compete for the same pixels. Supersedes the three-pane arrangement in the original layout, not D-5, which is about *which* views exist. |
| D-50 | Icons are SVG, tinted at load by substituting a `currentColor` token | One asset per icon instead of a folder of PNGs per theme, crisp at any DPI, and M9 recolours the whole set without shipping a second copy of it. Qt's SVG renderer does not resolve `currentColor`, so the substitution is textual and happens before rendering - which is worth writing down, because the token looks like it should work on its own. |
| D-51 | The menu bar implements hover-to-switch itself rather than relying on the platform | With a menu open, moving along the bar must walk between menus - every desktop does this. Qt usually provides it, but the open popup grabs the mouse and on some compositors (WSLg) the moves never reach the menu bar, so the behaviour silently goes missing. One event filter removes the dependence on what is underneath. Hovering deliberately does *not* open the first menu. |
| D-52 | BPM is a view over a fixed sample timeline: changing it moves the grid, not the material | Clips and keyframes are stored in samples (D-11, and the Time section of [03-data-model.md](03-data-model.md)), so a BPM change slides the grid underneath an arrangement that does not move. The consequence is worth stating plainly because it surprises people: material lined up to bars at 120 is no longer lined up at 124. The alternative — rescaling every clip start and keyframe time — makes BPM a destructive edit that silently resamples nothing but changes where everything is, and it cannot be undone cleanly when a clip's length is not a whole number of ticks. Set the tempo before arranging; the grid is a ruler, not a transform. |
| D-53 | The project's length is derived from its content, not stored | One less field that can disagree with the material, and nothing has to be maintained when a clip moves. Length is the end of the last clip on any channel; an empty project has zero length and renders nothing. Automation past that point is real but inaudible, so it does not extend it. The render range (F-53) defaults to this and can be overridden, which is where "I want the tail" is answered — not by storing an end marker somebody has to remember to drag. |
| D-54 | The master limiter is one fixed design, not a configurable one: brickwall, −0.3 dBFS ceiling, 1.5 ms lookahead, 50 ms release, internally delay-compensated | The project is not a mastering tool and a limiter with six controls is six more things to get wrong in a mix whose point is elsewhere. `limiter_on` stays a boolean. Lookahead is what makes it a limiter rather than a clipper, and compensating it internally is what keeps preview and render time-aligned and keeps the stems-sum test in M7 honest: stems skip the limiter (D-41), so an uncompensated lookahead would delay the master relative to them by a constant nobody had written down. No randomness anywhere in it, so F-36 survives. |
| D-55 | A master output meter in v1; per-channel meters are not | You cannot gain-stage 32 sources summing in the frequency domain by ear alone, and distance attenuation makes the relationship between a channel's fader and its contribution non-obvious — so the master meter is not a nicety, it is the only feedback that the number in the file is not clipping. Per-channel meters are a mixing console, which [00-overview.md](00-overview.md) puts out of scope; the parameters pane's gain field plus solo covers the same need at the rate this application needs it. |
| D-56 | The 24-bit render is dithered, with a seeded TPDF generator | Truncating float32 to 24-bit correlates the error with the signal, which is the textbook reason to dither, and at 24 bits the cost is inaudible either way — so the only real question is whether F-36's bit-identical promise survives. Seeding the generator from a constant makes it survive: the same render produces the same noise. Left unseeded it would not, and the determinism test would have caught it as a mystery rather than as this decision. |
| D-57 | Selection holds one kind of thing at a time, with multi-select inside that kind | Clips, keyframes and channels each have their own edit verbs, and a selection mixing a clip with a keyframe makes `Delete` ambiguous in a way no modifier fixes. Selecting a clip therefore clears any keyframe selection and vice versa. Within a kind, selection is plural and may span channels (F-51), because "move these four clips" is the common case and doing it one at a time is the thing people notice. |
| D-58 | Clip cut/copy/paste is in v1 | It looked like scope creep against "this is an arranger, not a DAW", and it is the opposite: duplicating a clip in place (`Ctrl+D`) is useless for the actual arranging gesture, which is taking a phrase from one channel to another. The model makes it cheap — a clip is a dataclass referencing media by id, so a paste is a construction, not a copy of any audio. |
| D-59 | Caches live in one user-level directory keyed by content hash, not in a `.3dim-cache/` beside the project | Every cached thing is already keyed by the hash of its input — peaks by media hash, prepared HRTF banks by SOFA hash and block size — so nothing about them is project-specific, and putting them beside the project made two projects using the same sample each compute their own pyramid, which contradicts F-9's "once per file". It also had no answer for a project that has never been saved and therefore has nowhere to sit beside. Supersedes the `.3dim-cache/` location described in earlier drafts of [03-data-model.md](03-data-model.md). |
| D-60 | `.3dim` records the version that wrote it, and no timestamps | The writing version is the first thing anyone wants when a project loads wrong, and `schema_version` does not carry it: two builds can write schema 1 and disagree about a default. Timestamps were considered and rejected — a `modified` field changes on every save, so every save produces a diff even when nothing about the music changed, which costs exactly the git-friendliness D-13 was for. The filesystem already knows when the file was written. |
| D-61 | Channel order is the order of the `channels` list; the stored `index` is dropped | Two homes for one fact, in the document whose own governing rule ([doc-system.md](doc-system.md) §2) is that every fact has exactly one. Reordering had to update both, and a file where they disagreed had no defined meaning — there was no rule saying which one wins, because there is no good answer. |
| D-62 | Solo is additive; any solo silences every non-soloed channel; an explicit mute still wins on its own channel | The additive part is what makes soloing two channels together possible at all, which is most of what solo is for here. Mute-beats-solo is the less obvious half and is chosen because mute is the more deliberate gesture: someone who muted a channel and then solos it was auditioning the rest, not asking for the mute to be quietly reversed. Bypassed channels obey solo like any other — bypass is about spatialisation, not about the mix bus (D-33). |
| D-63 | The output stream always opens at 48 kHz; the device and block size are selectable from M2 by command line and from M8 in preferences | D-11 fixes the engine at 48 kHz, and resampling the output inside the callback would put a second rate converter on the hot path to hide a problem better reported. If a backend refuses 48 kHz, that is reported (F-56) and the device list says which devices accept it. The command-line escape hatch exists because the preferences UI is M8 and the first sound is M2: five milestones in which a wrong default device makes the application look broken with no way out is not a gap worth accepting for the sake of tidiness. |
| D-64 | Autosave writes a sidecar recovery file and never touches the project | Silently rewriting someone's project file is the one autosave behaviour that can lose work rather than save it, and it breaks the promise that `Ctrl+S` is when your decisions become permanent. A sidecar beside the project, removed on a clean save or a clean exit, gives crash recovery without ever putting the application's judgement ahead of the user's. An unsaved project's sidecar goes to the user-level directory from D-59. |
| D-65 | Reported problems go to a notice centre, and it is built at M9 rather than M8 | [04-ui-spec.md](04-ui-spec.md) already promised that a bad theme is "reported... visible in the UI, not a line on stderr nobody reads", and F-47 and F-3 make the same promise for themes and missing media. There was no surface for any of it, and the general error surfaces sat at M8 — six milestones after M9 needs one and seven after F-3 does. Building it at M9, where the first requirement for it lands, costs a small widget; leaving it at M8 means M9 ships a promise it cannot keep and every milestone in between invents its own message box. |
| D-66 | Overlaid automation curves are each normalised to their own range; the value axis labels the focused curve | [04-ui-spec.md](04-ui-spec.md) promised both a multi-curve overlay and a value axis that auto-ranges per parameter, and those cannot both be literally true: `pos.x` in metres, `gain` in dB and `pan` in −1…+1 do not share an axis. Normalising each curve to its own range keeps the overlay readable — what you are comparing across curves is *shape and timing*, which is what an overlay is for — and labelling the focused curve keeps the numbers honest for the one you are editing. The alternative, stacked mini-axes, costs vertical space the panel does not have. |
| D-67 | Version floors in `pyproject.toml`, exact versions in a committed `uv.lock` | An application still publishes a wheel, and pinning exact versions in its metadata makes it uninstallable alongside anything else — so the floors stay, and they are floors with reasons (`numpy>=2.0` is D-38). Reproducibility is a different question and belongs in a lock file, which is what `uv` is already named for in [08-environment.md](08-environment.md). Recorded because [06-roadmap.md](06-roadmap.md) claimed "pinned dependencies" as delivered at M0 while neither mechanism existed. |
| D-68 | Undo and redo shortcuts are written out, not taken from `QKeySequence.StandardKey` | `StandardKey.Redo` resolves to `Ctrl+Y` on Linux and Windows, so the menu and [04-ui-spec.md](04-ui-spec.md)'s keyboard table disagreed inside one window — and the toolbar's own tooltip sided with the spec. Qt maps `Ctrl+` onto Command on macOS by itself, so writing `Ctrl+Shift+Z` is correct on all three. `StandardKey` is kept where it has no spec to contradict, and `Quit` keeps it with a `Ctrl+Q` fallback, because on several Linux platform themes it resolves to nothing at all. |
