# M2 — Media

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Specification: *Media
pool* in [04-ui-spec.md](../04-ui-spec.md), `MediaFile` and *Caches, not
project data* in [03-data-model.md](../03-data-model.md), *The output stream*
in [05-audio-engine.md](../05-audio-engine.md) · Workflow:
[09-workflow.md](../09-workflow.md)

| Phase | Status |
|---|---|
| [1 — The project in the window](phase_1_project_in_the_window.md) | ✅ |
| [2 — Decode and resample](phase_2_decode_and_resample.md) | ✅ |
| [3 — Content hash and relink](phase_3_hash_and_relink.md) | in progress |
| [4 — Peaks and the cache](phase_4_peaks_and_cache.md) | not started |
| [5 — The waveform widget](phase_5_waveform_widget.md) | not started |
| [6 — The media pool](phase_6_media_pool.md) | not started |
| [7 — Audition](phase_7_audition.md) | not started |

The order is dependency order. Everything after phase 1 edits a project the
window has to be holding; peaks need decoded audio and a hash to be keyed by;
the waveform draws peaks; the pool shows waveforms; and audition is last
because it is the only phase that needs an audio device, and so the only one
that cannot be finished on WSL.

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> you can import a folder, see waveforms, and double-click to hear a sample.

## Scope amended before the milestone started

Two changes to the roadmap's list, made while M2 is *not started*, which is
when [09-workflow.md](../09-workflow.md) says scope may change freely.

**The project in the window is added, as phase 1.** M1 built the model, the
`.3dim` file and the undo stack headless, by design — and nothing in the
roadmap ever wired them to the UI. File › New, Open, Save and Save As and
Edit › Undo and Redo are still disabled, with tooltips saying they arrive at
M1, which is finished. M2 cannot pass without them: importing is an edit, F-4
says every edit is undoable, and F-3's missing media is only ever discovered
by opening a project.

**`--device`, `--block` and the 48 kHz stream rule move here from M3.** D-63
and [05](../05-audio-engine.md) both say the flags exist "from M2", because
M2's audition is the first sound — and the roadmap's M3 bullet gives the same
reason while sitting one milestone too late. The decision log wins; the
roadmap is corrected.

## What this milestone does not deliver

| Not here | Where |
|---|---|
| Dropping a sample onto the timeline | M3. M2 builds the drag *source*; the timeline is the target |
| Waveforms inside clips (F-21) | M3, reusing phase 5's widget |
| The relink *dialog* | M8, before beta (D-84). M2 builds relinking — the command and the hash check — and M8 hangs a dialog off the notice |
| The parameters pane's media view | the pane arrives with the selections that drive it; the waveform widget is built so it can be reused there |
| Channel-aware playback, gain, transport | M3. Audition is deliberately trivial: one sample, straight to the output |
| Preferences for device and block size | M8. Command-line flags until then (D-63) |
| Autosave and crash recovery | M8 (F-49) |

## Questions the plans must settle

Found while writing the phase docs, and left open on purpose — each is its
phase's first decision.

- ~~**Is F-5's "fallback decoder" still needed?**~~ No — every platform's
  wheel carries libsndfile 1.2.2 with MP3 (D-86, phase 2).
- ~~**What does a file with more than two channels become?**~~ Refused, with
  the count in the reason (D-87, phase 2).
- **What is hashed, and with what?** The bytes on disk or the decoded audio,
  and how long a two-gigabyte WAV may take. Phase 3.
- **Where exactly is the cache, and who resolves it?** `03` gives literal
  paths per platform (`~/.cache/3dimmersive`); Qt's cache location for this
  application is a different path; and `peaks.py` lives in `core/`, which
  N-5 keeps free of Qt. Phase 4 — and the test isolation M9 built does not
  yet redirect the cache directory.
- **PortAudio is not installed here, and not on CI's Linux runner.**
  `import sounddevice` fails on this WSL venv with *PortAudio library not
  found*: on Linux the wheel does not bundle it. Phase 7 has to decide what
  CI installs, what `08` tells a developer to install, and how audition is
  tested without a device.

## Notes

Appended as phases complete.

**Phase 1.** The window holds a document — the project, its undo stack and
its file — and File › New, Open, Save, Save As and Edit › Undo, Redo work
through it. One decision: the open project is a Qt-free `Document` in
`core/`, and every edit goes through it (D-85). The one confirmation the
application is allowed now exists — Save, Discard or Cancel — and Save goes
ahead only if the save worked.

The finding that matters beyond the phase is about the tests. Every window
the suite built was still alive when it finished, and each made the
next slower to build; freeing them took the suite from three minutes to
eight seconds. A guard now fails any test that reaches a real modal dialog
rather than letting it hang — except `QMessageBox.question`, which runs its
loop out of reach and so is never used. Eighteen mutations, none surviving.

**Phase 2.** `core/io/media.py` decodes every format F-5 names to float32 at
48 kHz, or refuses with a reason, and never raises on input. Two decisions:
libsndfile alone, with no fallback decoder, backed by inspecting the bundled
library in every platform's wheel (D-86); and more than two channels refused
rather than guessed at (D-87). Float files keep their overs. The sweep
disproved the plan's most confident claim — `soxr` at equal rates is exact,
so skipping it at 48 kHz is a saving rather than a safeguard — and one of the
questions in this README is answered: the fallback decoder is not needed.
