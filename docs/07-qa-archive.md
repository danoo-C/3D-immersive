# 07 — QA Archive

> **Status: CLOSED.** Every question on this page has been answered and merged
> into the specification. Nothing here is an open decision — this is the record
> of how the docs got their shape, kept so the reasoning behind a decision can
> be recovered without re-running the conversation.
>
> Answered: **2026-09-20**. Merged into docs: **2026-09-20**.
> Short-form decisions live in the log in [01-requirements.md](01-requirements.md).

**Legend** — ✅ answered directly · ☑️ resolved by accepting the proposed default
· 🔧 tuning left to a listening test at the named milestone

---

# A. Structured rounds

Questions posed as multiple choice. Rejected options are kept deliberately —
knowing what was turned down is usually more useful later than knowing what was
picked.

## Round 1 — Foundation

### QA-1 ✅ Which stack should we build on?
| | Option |
|---|---|
| ✅ | **Python** — PySide6 + numpy/scipy + sounddevice |
| | C++ / JUCE |
| | Python UI + native engine from day one |

**Rationale for the recommendation:** UI-heavy app; numpy gives C-speed DSP;
export is offline so quality is never GIL-limited; the audio callback is a
single clean seam to port later. C++ only wins for plugin export (see QA-27).

→ D-1, [02-architecture.md](02-architecture.md)

### QA-2 ✅ What does v1 need to do when you hit play?
| | Option |
|---|---|
| ✅ | **Realtime preview** — live binaural playback following the playhead, ~20 ms latency acceptable |
| | Offline render only |
| | Preview now, but with a simplified HRTF path |

→ D-3, F-33, N-1

### QA-3 ✅ How deep should the spatial model go in v1?
| | Option |
|---|---|
| | 2D direction + distance *(recommended at the time)* |
| | Direction only |
| ✅ | **Full 3D: + elevation** |
| | Full 3D + room reverb |

**Consequence flagged and handled:** elevation cannot be expressed in a
top-down-only workspace, which forced QA-5.

→ D-4, F-23, [03-data-model.md](03-data-model.md)

### QA-4 ✅ Where will you actually run the app?
| | Option |
|---|---|
| | Windows native |
| | Linux native |
| ✅ | **Cross-platform** — Windows, macOS, Linux |
| | WSL2 is fine |

**Standing caveat:** the dev machine is WSL2, where audio latency is poor and
device control limited. `core/` is testable there; the preview and the M4
benchmark are not. See the environment note in [06-roadmap.md](06-roadmap.md).

→ D-2, N-6, M8

## Round 2 — Model & layout

### QA-5 ✅ How should the workspace let you edit height?
| | Option |
|---|---|
| ✅ | **Two ortho views** — top (X/Y) primary + front (X/Z) beside it |
| | Top view + Z slider in the param pane |
| | Orbitable 3D view |

> **Answer, verbatim:** *"the two ortho views, but a fixed 3d view for read
> only. can look nice on videos."*

So the workspace became **three** panes: two editable orthographic views plus a
read-only fixed-camera 3D view. The lack of camera controls on the third is
intentional — it cannot be knocked out of place mid-recording.

→ D-5, F-24, [04-ui-spec.md](04-ui-spec.md); the video angle is QA-35

### QA-6 ✅ What exactly is a "channel"?
| | Option |
|---|---|
| ✅ | **A track holding many clips** — one colour, one spatial position, one automation set; all its clips emit from that moving point |
| | One channel = one sample |
| | Track, but with per-clip position override |

This was the largest structural question — the original spec read both ways.

→ D-6, F-10, [03-data-model.md](03-data-model.md)

### QA-7 ✅ When you drag a clip, what happens to its motion keyframes?
| | Option |
|---|---|
| | Pinned to the timeline *(recommended at the time)* |
| | Travels with the clip |
| ✅ | **Pinned, but hold Shift to drag both** |

→ D-7, F-31, the Shift+drag entry in the keyboard table

### QA-8 ✅ What form should the keyframe explorer take?
| | Option |
|---|---|
| | Param tree + lanes inside the timeline *(recommended at the time)* |
| ✅ | **Self-contained curve editor** with its own time axis |
| | Numeric keyframe list |

**Mitigation added because of this choice:** a self-contained editor risks
drifting out of alignment with the timeline, so both widgets observe one shared
`TimeAxis` object that owns scroll and zoom. Neither owns it.

→ D-8, F-30, the risk register in [06-roadmap.md](06-roadmap.md)

---

# B. Defaults proposed and accepted en bloc

Offered as "object in one line and I'll change it". None were objected to.

| # | | Default | Landed in |
|---|---|---|---|
| QA-9 | ☑️ | Non-destructive clip editing; source files never modified | D-12, F-14 |
| QA-10 | ☑️ | Full undo/redo, every edit a command object from day one | D-14, F-4 |
| QA-11 | ☑️ | Per-clip gain + fades; per-channel volume / mute / solo | F-12, F-15 |
| QA-12 | ☑️ | Snap to grid **and** clip edges; 1/1 → 1/32 plus triplets | F-16, F-17 |
| QA-13 | ☑️ | Single global BPM, no tempo map | D-26 |
| QA-14 | ☑️ | Ruler switchable bars:beats ↔ min:sec | F-19 |
| QA-15 | ☑️ | No time-stretch or pitch-shift in v1 | [00-overview.md](00-overview.md), out of scope |
| QA-16 | ☑️ | Automatable: `pos.x`, `pos.y`, `pos.z`, `gain`; linear / ease / hold | F-28, F-29 |
| QA-17 | ☑️ | Keyframes written only when automation is explicitly armed | F-32, the `ARM` toggle |
| QA-18 | ☑️ | Fixed layout with splitters, not floating docks | D-15 |
| QA-19 | ☑️ | Waveforms drawn in clips, backed by a peak cache | F-9, F-21 |
| QA-20 | ☑️ | Engine fixed at 48 kHz float32; imports resampled on load | D-11, F-6 |
| QA-21 | ☑️ | Export 24-bit stereo binaural WAV + optional per-channel stems | F-34, F-35 |
| QA-22 | ☑️ | Project is JSON referencing audio by relative path, no bundling | D-13, F-2 |
| QA-23 | ☑️ | Dry HRTF only — no reverb or early reflections | D-9 |
| QA-24 | ☑️ | Sources move; listener fixed at origin | D-10, F-22 |
| QA-25 | ☑️ | Stereo source files downmix to a mono point source | D-16 |
| QA-26 | ☑️ | Tests on the engine/timeline core, none on UI | N-5, M1 |
| QA-27 | ☑️ | No VST hosting or plugin export, ever | D-18 |
| QA-28 | ☑️ | Dark palette with purple accent, exact hexes proposed | [04-ui-spec.md](04-ui-spec.md) |

> **QA-26 partly superseded, after this archive closed.** "None on UI" did not
> survive contact with M0. There are UI tests today — the shell's structure,
> the icon set, the palette's contrast ratios, the stylesheet parsing at all —
> and `pytest-qt` is a declared dependency. They run headless under
> `QT_QPA_PLATFORM=offscreen`, so N-5 is untouched: the claim that mattered
> was that `core/` needs no display, not that nothing else may be tested.
>
> What QA-26 was really answering is still right, and is worth keeping in
> those words: no test drives a widget to check that a drag *feels* right.
> The UI tests assert structure and rules the specification states — that a
> disabled action explains itself, that redo is `Ctrl+Shift+Z` — which are
> exactly the claims a document can make and a human reviewer will not
> re-check every release. Recorded here rather than left as drift, per
> [doc-system.md](doc-system.md) §3.

---

# C. Follow-up assumptions, confirmed

These were raised as still-open after the structured rounds, each with a
proposed assumption. All assumptions were accepted.

### QA-29 ☑️ The truncated spec *(was Q-1)*
The original `README.md` ends mid-sentence: *"the bottom part is a resisable
config/param"*. The intended contents were unknown.

**Resolved as:** a context-sensitive parameters pane, contents driven by the
current selection — media file / channel / clip / nothing. Table in
[04-ui-spec.md](04-ui-spec.md). → D-19

> ⚠️ The original text was never recovered. This is a reconstruction that fits
> the layout, not a transcription. If the missing wording turns up and says
> something else, this is the decision to revisit first.

### QA-30 🔧 Default HRTF dataset *(was Q-2)*
Needs full-sphere elevation coverage, a permissive licence, and a bundle size
that survives PyInstaller. Candidates: SADIE II, ARI, full-sphere KEMAR, Listen.

**Resolved as:** pick by listening test during **M4**; it is now an explicit M4
task rather than an open question.

### QA-31 ☑️ Clip overlap behaviour *(was Q-3)*
**Resolved as:** magnetic — dropping onto an occupied span trims the existing
clip, with a modifier to reject the drop instead. Clips on a channel never
overlap. → D-23

### QA-32 ☑️ Distance model curve *(was Q-4)*
Strict `1/r` is physically correct but makes sources vanish faster than most
people want.

**Resolved as:** `(ref_distance / r) ** rolloff`, `rolloff` default 1.0 and
exposed in project settings, `r` clamped to 0.2 m. Tuned by ear at M4. → D-21

### QA-33 ☑️ Air absorption *(was Q-5)*
**Resolved as:** not in v1. Recorded because a distance-driven one-pole low-pass
is the cheapest available improvement to perceived depth, and is the first thing
to try if the spatial image feels flat during M5. → D-22

### QA-34 ☑️ Freehand motion paths *(was question 22 of the sweep)*
Drawing a path on the canvas — sketch a circle, the sound orbits.

**Resolved as:** not in v1. No default had been proposed for this one, so it is
called out explicitly rather than quietly dropped. Motion-path *presets* (orbit,
flyby, random walk) remain on the "later, maybe" list. → D-25

### QA-35 ☑️ What the 3D view is ultimately for *(was Q-6)*
Follows from the verbatim note in QA-5.

**Resolved as:** screen recording only for v1, so a `QPainter` isometric
renderer is sufficient. A frame-accurate video *file* export would need an
offscreen renderer decoupled from display refresh, probably OpenGL — left as a
seam, not built. → D-24

### QA-36 ☑️ Per-channel HRTF override *(was Q-7)*
Appeared in an early UI draft.

**Resolved as:** cut. Cheap to build, but mixing HRTF sets within one mix sounds
inconsistent. Removed from the channel parameters table deliberately rather than
left to rot. → D-20

### QA-37 ☑️ Stereo source handling *(was Q-8)*
Downmix to mono, or treat as two points with a width parameter — the latter is
nicer for pads and ambiences, which are often exactly what you want placed wide.

**Resolved as:** downmix in v1 (D-16); revisit after M5 when it is possible to
hear what is missing.

> **Partly superseded, after this archive closed.** Per-channel HRTF bypass
> (D-32) gives stereo material a route that keeps its image intact. D-16 still
> governs stereo sources that *are* spatialised; bypass is the exception.

### QA-38 ☑️ Project file extension *(was Q-9)*
**Resolved as:** `.3dim`, no OS file-association or icon registration in v1.

---

# D. The original question sweep

Every question asked in the first pass, kept verbatim in intent, each with
where it ended up. Most were folded into sections A–C above; this table exists
so nothing from the original sweep is unaccounted for.

## Model & scope
| # | Question | Resolution |
|---|---|---|
| 1 | Is a channel a track holding many samples, or one channel per sample? | QA-6 — track holding many |
| 2 | Do keyframes live on the channel or the clip? | QA-7 — channel, absolute time, Shift couples |
| 3 | Can multiple clips share one channel, and thus one position? | Yes, follows from QA-6 |
| 4 | What is the deliverable — stereo binaural WAV? Stems? Project file? | QA-21, QA-22 — all three |

## Spatialization
| # | Question | Resolution |
|---|---|---|
| 5 | Elevation, or strictly horizontal plane? | QA-3 — full 3D with elevation |
| 6 | Does distance just pan, or also attenuate and filter? | QA-32 attenuate; QA-33 no filtering in v1 |
| 7 | Dry HRTF, or reverb / early reflections? | QA-23 — dry only |
| 8 | Built-in HRTF, or user-loadable SOFA? | Both — F-27; default set is QA-30 |
| 9 | Can the listener head rotate and be keyframed? | QA-24 — no, fixed at origin |
| 10 | What happens to a stereo source file? | QA-37 — downmix to mono point |
| 11 | How many simultaneous channels? | 32 moving sources, as N-1 |
| 12 | Head tracking? | No — out of scope |

## Timeline & editing
| # | Question | Resolution |
|---|---|---|
| 13 | Non-destructive crop/trim? | QA-9 — yes |
| 14 | Per-clip fades and gain? Per-channel volume/mute/solo? | QA-11 — yes to all |
| 15 | Snap to grid only, or clip edges too? Which divisions? | QA-12 — both; 1/1→1/32 + triplets |
| 16 | Global BPM or tempo changes? | QA-13 — single global BPM |
| 17 | Bars:beats or min:sec ruler? | QA-14 — switchable |
| 18 | Full undo/redo? | QA-10 — yes, command pattern from day one |
| 19 | Time-stretch or pitch-shift? | QA-15 — no |

## Keyframes & automation
| # | Question | Resolution |
|---|---|---|
| 20 | What is automatable besides position? | QA-16 — gain |
| 21 | Interpolation types? Bezier handles? | QA-16 — linear / ease (bezier) / hold |
| 22 | Auto-write on drag, or explicit arm? | QA-17 — explicit `ARM` toggle |
| 23 | Can you draw a motion path on the canvas? | QA-34 — not in v1 |
| 24 | Curve editor or list in the right panel? | QA-8 — self-contained curve editor |

## UI
| # | Question | Resolution |
|---|---|---|
| 25 | What was the truncated sentence? What is in the config/param pane? | QA-29 — reconstructed as a selection-driven params pane |
| 26 | Strictly top-down, or orbitable 3D? | QA-5 — two ortho views + read-only 3D |
| 27 | Reference grid/rings? Position snapping? | Rings at 1 m intervals; no position snapping in v1 |
| 28 | Waveforms inside clips? | QA-19 — yes, with a peak cache |
| 29 | Dockable panels or splitters? | QA-18 — splitters |
| 30 | Menu bar contents? | File / Edit / View / Transport / Render / Help |
| 31 | Where do transport controls live? | Toolbar directly under the menu bar; `Space` plays |
| 32 | Do you have a purple hex in mind? | QA-28 — palette proposed and accepted |

## Practical
| # | Question | Resolution |
|---|---|---|
| 33 | Which OS do you actually run this on? | QA-4 — cross-platform, with the WSL2 caveat |
| 34 | Just for you, or shipped to other people? | Shipped — M8 packages for all three platforms |
| 35 | Tests from the start? | QA-26 — yes on core, none on UI |
| 36 | VST hosting or plugin export, ever? | QA-27 — never; this is what protects D-1 |
