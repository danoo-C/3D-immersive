# M1 · Phase 5 — Project I/O

**Status:** in progress · **Plan:**
[plans/phase_5_project_io.md](plans/phase_5_project_io.md)

## Goal

`core/io/project_io.py` writes a project to a `.3dim` file and reads it back
equal. With a `schema_version`, a migration hook that has nothing to migrate
yet but exists so the first migration is not also a refactor, and the
`app_version` stamp from D-60.

This phase closes the milestone: *built in code, edited, undone, saved,
reloaded and compared equal.*

## Scope

**In:** serialising every entity from
[phase 1](phase_1_dataclasses.md); UTF-8 JSON, pretty-printed with sorted keys;
`schema_version` and the forward-migration hook; `app_version`; media paths
written **relative to the project file** (F-2, D-13); reading a file that is
missing fields a later version added, and defaulting them.

**Out:** the missing-media relink dialog → M8; this phase reports a missing
file as data and does not resolve it. Decoding anything the paths point at →
M2. Autosave and the recovery sidecar (F-49, D-64) → M8. The notice surface
that displays a load problem (F-56, D-65) → M9; here a load returns its
problems, and something later shows them.

## Acceptance

- [ ] **Round-trip equality.** A project built in code, saved and reloaded
      compares equal — the milestone's own acceptance, and the reason
      [phase 1](phase_1_dataclasses.md)'s equality had to be load-bearing.
- [ ] The file is byte-identical across two saves of the same project: sorted
      keys, fixed float formatting, no timestamps (D-60). A project that
      rewrites itself differently every save is unusable in git, which is what
      D-13 was protecting.
- [ ] `app_version` records the build that wrote the file and is **not**
      `schema_version` (D-60). A project that loads wrong is a bug report, and
      the writing version is the first thing anyone asks for.
- [ ] Media paths are relative to the project file, and a project plus its
      audio survives being moved to another directory — and to another
      platform, which means separators are normalised on write rather than
      whatever `os.sep` happened to be (F-2, D-13).
- [ ] A file whose `schema_version` is older than current loads through the
      migration hook; a file with fields the current version does not know is
      loaded, not rejected. Both have a test even though there is nothing to
      migrate yet, because the first real migration should be a function body
      and not a redesign.
- [ ] A **malformed** file — bad JSON, a missing required key, a clip whose
      `offset + length` exceeds its media — fails with a report naming what is
      wrong and where, and never leaves a half-built project behind.
- [ ] Missing media is reported and is **not fatal** (F-3): the clip survives,
      the `MediaFile` is marked missing, and the project loads. Relinking is
      M8's; being loadable without the audio is this phase's.
- [ ] A deliberately hand-edited `.3dim` in `tests/fixtures/` loads — the
      format is meant to be human-editable (F-2 calls it JSON for a reason),
      and a fixture written by hand catches the schema drifting away from what
      a person would reasonably type.

## Implements

F-1, F-2, F-3. D-13, D-60, and the *Project file* section of
[03-data-model.md](../03-data-model.md), which owns the schema. The migration
discipline is the one [04](../04-ui-spec.md) points at for `.3dimtheme` too,
though that is M9's separate format.

## Notes

Appended while building.
