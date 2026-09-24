# 06 — Roadmap

Ten milestones. Each ends at something you can actually run and judge, not at
an internal refactor.

**The file order is the build order; the numbers are identifiers, not
positions.** M9 is built third, straight after M1, and sits below it here.
It is numbered 9 because renumbering M2-M8 to make room would invalidate every
reference to them in every document, commit message and code comment - see
[doc-system.md](doc-system.md) §3.

This file stays at the milestone level and is the index of truth for milestone
status. The phase-by-phase breakdown of a milestone lives in its own directory
— `docs/m1_core_model/` and so on — created when that milestone starts. See
[09-workflow.md](09-workflow.md). The ordering is driven by one principle: **de-risk the
audio engine early**, because it is the only part that could invalidate the
choice of Python.

---

## M0 — Scaffolding ✅ *complete*
*Nothing audible.*

- `pyproject.toml` (hatchling), `uv` environment, dependency floors with
  reasons plus a committed `uv.lock` for reproducibility (D-67)
- `pip install -e ".[dev]"`; absolute imports enforced by `ruff` `TID252`
- Package skeleton per [02-architecture.md](02-architecture.md)
- `ruff` + `mypy` + `pytest` configured, CI running them on Linux/macOS/Windows
- `theme.py` with the palette, and a main window with the splitter layout and
  empty labelled panels

**Done when:** `python -m immersive` shows the dark, empty, correctly-proportioned shell.

**Delivered.** `pyproject.toml` (hatchling, src-layout, `TID252` banning
relative imports), the full package skeleton, `ruff` + `mypy` + `pytest`
configured and passing, GitHub Actions across Linux/macOS/Windows on 3.11 and
3.13, `theme.py` holding the palette, and a `MainWindow` with all seven regions
as labelled placeholders — since revised: the workspace became two tabs (D-49),
the transport grew an SVG icon set (D-50) and the palette moved to VS Code's
greys (D-44). The suite passes, and covers the palette's contrast rules, the
icon set, the shell's structure, the packaged distribution, the documentation
invariants from [doc-system.md](doc-system.md) §7, and the import-graph test —
which carries its own test proving the detector is not passing vacuously while
`core/` is still empty. Deliberately no test count here: it is exactly the
kind of number §2 of that document warns about.

**Corrected after a gap review.** Three claims above were not true when they
were written: dependencies were floors with no lock file (now D-67 and a
committed `uv.lock`), `pyproject.toml` declared MIT with no `LICENSE` in the
tree, and CI installed the package editable — which is the one path that does
*not* exercise the wheel, so D-27's stated benefit was not being collected.
CI now builds the wheel and installs it into a clean environment.

---

## S0 — Listening spike (throwaway) ✅ *complete*
*Not a milestone. A script whose only job is to be listened to.*

Phases: [`docs/s0_listening_spike/`](s0_listening_spike/README.md)

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
| `front_back_bursts.wav` | pink-noise bursts sweeping front → overhead → behind | elevation and front/back work |

It also prints per-block processing time, mean and p99 — an early data point
for the M4 benchmark.

**Constraints:** numpy/scipy plus `sofar` and `soxr`, nothing else. Not
generalised, not tidied, never imported by the package, never moved into
`src/`. If it turns out to be useful twice, it gets rewritten properly inside
the package. One file plus its checks, readable top to bottom in one sitting,
because the spike's whole job is to be *trusted* by someone deciding whether
the design is sound.

**There was a line budget here and it has been removed**, which is worth
explaining rather than quietly dropping. It was "~300 lines", raised to "~450"
during phase 2, and phase 2 finished at 506 with two phases still to go. Both
numbers were estimates of *code* against a budget measured in *total lines* —
the file is 49% code, 30% comment and docstring, 21% blank — and a third
estimate from the same source would be worth no more than the first two.

What the count was standing in for is the list above, and every item on that
list is checkable in a way a line count is not. The prose it was implicitly
penalising is load-bearing: the reason the cepstral `nfft` is 8192 and not the
textbook 1024 is four lines of measured table in a comment, and deleting it to
save lines would delete the finding.

Two phases of evidence say the honest total is somewhere near 750. If the
script ever reads like a library rather than a script, that is the thing to
act on, and it is visible without counting anything.

**Done when:** the four files exist, they have been listened to on headphones,
and the set the spike ran on is recorded — by name, version and licence — as
the leading candidate for the bundled default. Choosing that default stays
QA-30's, at M4. Feeds QA-30 and M4.

**Delivered, and it answered the question it was built to ask.** D-37 was
decided by ear: an uncrossfaded fast orbit was described, unprompted, as
*"horrible, like a dial up tone under the sound"* against *"a clean tone"*
crossfaded. The per-block filter crossfade is necessary and it works, and
three milestones of design now rest on something heard rather than argued.
`orbit_noise.wav` was *"so realistic"*, the zipper test found no buzz, and the
front/back sweep was followable with eyes closed. Full verdicts in
[phase 5's Notes](s0_listening_spike/phase_5_listening.md).

The spike also produced the numbers M4 inherits: `max_itd_samples` 39 and so a
convolution `nfft` of 1024, matching this document's cost estimate; 0.20 ms
mean and 0.44 ms p99 per block for one source against a 10.7 ms budget, with
the direction lookup in the loop. N-1's thirty-two sources remain M4's.

Two findings changed the specification. **D-70** — the crossfade's benefit
shrinks as a source speeds up, 33.7 dB at 1 rev/s down to 8.6 dB at 8 — and
with it a correction in place to [05](05-audio-engine.md), whose claim that an
uncrossfaded held tone is a *clearly* audible buzz is too strong at the slow
end. And the front/back stimulus was replaced mid-phase: single-sample clicks
could not carry their own test, and 40 ms pink-noise bursts on the identical
trajectory could. The table above names the file that shipped.

Per its own terms the spike is **not** promoted: nothing in it moves into
`src/`. M4 rewrites the pipeline properly in `audio/hrtf/`, with the phase
Notes as the record of what was already learned the hard way.

---

## M1 — Core model, headless ✅ *complete*
*No UI work at all.*

- ✅ Pin `numpy>=2.0` in `pyproject.toml` — a hard floor, not a preference
  (D-38); the realtime zero-allocation rule depends on it. Done early, during
  S0, because the spike exercises the same `rfft`/`irfft` path
- `model.py`, `curves.py`, `time.py` dataclasses
- Curve evaluation: linear, hold, ease with bezier solve
- Snapping and bars:beats ↔ samples conversion
- `commands.py` undo stack + first concrete edits
- `project_io.py` save/load with `schema_version` and a migration hook
- The import-graph test that forbids Qt, `sounddevice`, `immersive.ui` and
  `immersive.audio` inside `core/` (sketch in [02-architecture.md](02-architecture.md))
  — ✅ exists from M0; phase 1 is the first time it has anything to bite on

Phases: [`docs/m1_core_model/`](m1_core_model/README.md)

**Done when:** a project can be built in code, edited, undone, saved, reloaded
and compared equal — all in pytest, with no window open.

**Delivered, and the acceptance is one test.** `model.py`, `curves.py`,
`time.py`, `commands.py`, `edits.py` and `core/io/project_io.py`, in five
phases: the entity spine and its equality, curve evaluation with the bezier
solve, bars:beats and snapping, the undo stack and the first seven commands,
and the `.3dim` file. A project is built in code, edited through the stack,
undone, redone, saved, reloaded and compared equal — with no window open and
no audio device, which is N-5 and which is why the whole milestone was
verifiable on WSL.

Three decisions came out of the file format: media paths are absolute in
memory and relative on disk (D-71), missing media is a field excluded from
equality (D-72), and a key the schema does not know is dropped rather than
preserved or refused (D-73). The `.3dim` sorts its keys, coerces its numbers,
writes no timestamp (D-60), records the build that wrote it, and is written
through a temporary file so an interrupted save cannot truncate the project
that was already there.

**The phase found `03`'s own worked example of the file format was not
loadable** — the backing mix's clip referenced a media id that was not in its
pool. It is corrected, and a test now lifts that listing out of the document
and opens it on every run. Every other test in the phase round-trips the
module against itself and none of them could have noticed.

Two lessons that M9 inherits with `.3dimtheme`, and that the phase Notes
argue at length: a round trip proves the reader and the writer *agree*, not
that either is right, so every assertion pinning a format has to read the
file; and a cross-platform behaviour asserted only end to end is asserted on
one platform, because CI's only leg is Linux. Thirty-eight mutations were
named across the phase and four survived their first run — all four real, all
four now caught.

---

## M9 — Theming ✅ *complete*
*Built after M1. Numbered last, built third — see the note at the top.*

Phases: [`docs/m9_theming/`](m9_theming/README.md)

Colour is currently thirteen constants in `theme.py` and a QSS template. That
is enough for a shell and not enough for an application: it cannot be changed
without editing source, and by M6 there will be clips, waveforms, keyframes and
three spatial views all reaching for colours that no file names.

- A `Theme` object with `tokens` and `groups`, replacing the flat constants.
  No widget anywhere names a hex (F-44)
- The `.3dimtheme` format: versioned JSON, parsed, validated, merged over the
  built-in default (F-45, F-46, D-45, D-46)
- The built-in theme moved out into a bundled `.3dimtheme`, loaded through the
  same path as a user's (D-47), via `importlib.resources` (D-30)
- Discovery of the user theme directory, and switching without a restart
  (F-48) from a `View > Theme` menu — the **Preferences** UI stays at M8
- **The notice centre** (F-56, D-65): the status-bar line, the unread count
  and the list behind it, specified in the *Notices* section of
  [04-ui-spec.md](04-ui-spec.md). It lands here because this is the first
  milestone that has something to report and a requirement — F-47 — that says
  it must be visible in the UI. M2's missing media (F-3) is the next caller,
  and M2 comes after this one
- Failure handling: missing, malformed, unknown keys, bad colours, newer
  schema — all non-fatal and all reported through that surface (F-47, D-48)
- A contrast report for a loaded theme, advisory for user themes and enforced
  by test for the built-in

Full specification in the *Theming* section of
[04-ui-spec.md](04-ui-spec.md).

**Why here and not at M8:** every milestone after this one paints new widgets.
If the vocabulary does not exist yet, each of them invents its own colours and
M8 becomes an archaeology exercise across six milestones of hardcoded hexes.
Doing it after M1 costs one milestone now and saves that.

**Why not before M1:** the model comes first, and the two phases that need
widgets to point at would have nothing to name.

⚠️ M9 does **not** deliver a complete token vocabulary — it cannot. The
widgets for M3-M6 do not exist yet. It delivers the *system*, and every
milestone from here on adds its own groups to `04` as it builds them. That
obligation is written into the spec, because the failure mode of a theme
system is a widget quietly hardcoding a colour two milestones later.

**Done when:** the application's entire palette lives in a bundled
`.3dimtheme`, a user theme file that changes only the accent visibly works,
and a deliberately broken theme file is reported without preventing startup.

**Delivered, and each clause of the acceptance is a test.** `theme.py` holds
no colour: the palette is `assets/themes/vscode_dark.3dimtheme`, read through
the same loader as a user's and held to the 4.5:1 contrast rule off disk.
`theme_io.py` reads, merges and writes the format and never raises on input;
`View > Theme` lists the user's themes, rescans on opening, switches without a
restart and remembers the choice by path. A theme that changes only the accent
changes every stylesheet rule that resolves to it and no other byte, and the
new colour is found in rendered pixels. A deliberately broken theme is listed,
selectable, reported through the notice centre — status line, count, one line
per problem — and leaves the application painting on what it could salvage.

Ten decisions, D-74 to D-83: one token vocabulary rather than the two `04`
carried, channels as their own list, one active theme read at call time, the
format's module and its report's severities, no fallback palette, a cached
built-in reached through a deferred import, a Qt-free notice model, a repaint
that walks the widget tree, and the choice stored as a path. The notice centre moved here from M8 before the milestone started
(D-65), and M2's missing media is its next caller.

**The most useful check was a screenshot**, and both of its findings were
layout rather than colour — a hidden status-bar widget that moved every panel
the first time anything was reported, and wrapped notice rows that cut off the
problem lines. Two things pass forward. The repaint walk reaches only
`QWidget`s, so M3's timeline items must be rethemed by their view or read
their colours at paint time. And the playhead half of phase 4's accent line
arrives with the playhead, at M3.

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
- Selection: multi-select across channels, rubber band, and the one-kind rule
  (F-51, D-57)
- Cut / copy / paste of clips within and between channels (F-50, D-58)
- Transport and keyboard shortcuts, including the playhead readout (F-52)
- **Non-spatial** playback: scheduler + clip reads + gains → straight stereo
- The master meter and its clip indicator (F-54) — the first milestone that
  produces a level at all, and the last comfortable one to add it before M4
  starts summing 32 sources
- `--device` and `--block` command-line flags, and the 48 kHz stream rule
  (F-55, D-63). Preferences promotes them at M8; the gap between the first
  sound and M8 is otherwise five milestones with no way to pick a device

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
- The master bus: gain, and the fixed-design limiter with its lookahead
  compensated internally (D-54) — the compensation is what keeps M7's
  stems-sum test honest, since stems skip the limiter (D-41)
- Implicit 32-sample edge fades in the scheduler (D-42)
- The zero-allocation test on `process()`
- **A benchmark against N-1: 32 moving sources, 512 block, zero xruns**

**Done when:** positions set numerically in a test project are audibly, correctly
placed — and the benchmark passes. If it does not pass here, we find out now,
with the port seam still tiny, rather than after the UI is built on top.

---

## M5 — Spatial workspace
- Top (X/Y) and front (X/Z) ortho views, sharing the workspace's first tab
  (D-49): head glyph, rings, channel icons
- Drag to position, live during playback
- Motion trails and keyframe diamonds drawn from the curves
- Read-only isometric 3D view via `QPainter`, in the workspace's second tab
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
- Render dialog: range, block size, stems toggle, output path. The range is
  the whole project (derived, D-53), the loop region, or typed (F-53)
- Seeded TPDF dither on the 24-bit conversion (D-56) — unseeded would make
  F-36's determinism test fail as a mystery rather than as a decision
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

Beta is a line drawn through this milestone rather than a milestone of its own
(D-84). The first list is what beta needs; the second follows it.

**Before beta**

- `PyInstaller` bundles for Windows and Linux
- README with install instructions for those two platforms
- Autosave and crash recovery: the sidecar file, and the offer on next launch
  (F-49, D-64)
- Missing-media relink dialog, hung off the notice built at M9 — the first of
  the actions that hang off individual notices

**After beta**

- Preferences: audio device, block size, HRTF set, and the theme picker
  promoted out of the `View` menu (the theme *system* is M9). The device and
  block flags from M3 become fields here (F-55)
- Session persistence: window geometry, splitters, recent projects
- Error surfaces **promoted, not invented**: the notice centre is M9 (D-65);
  M8 adds the remaining actions that hang off individual notices and the
  first-run polish around them
- Empty states and a first-run sample project
- The macOS bundle, with signing and notarisation
- README install instructions for macOS

**Beta when:** somebody who is not you installs it on Windows or Linux from a
bundle, takes a folder of their own samples to a rendered binaural WAV —
import, arrange, place, animate, render — without being helped, and a crash
along the way costs them no more than the last autosave interval.

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
