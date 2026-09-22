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

### Step 1 — the decisions, and the writer

D-71, D-72 and D-73 are in the log; `save()` writes a `.3dim` and refuses to
write anything it should not. The reader is step 2, so nothing here asserts a
round trip — a writer and a reader wrong in the same direction round-trip
perfectly, and every assertion in `tests/test_project_io.py` reads the file
instead of the model.

**Eleven mutations were named in the plan; ten were caught on the first run
of the finished suite.** The one that survived is worth the space, because it
is a hole in the *test environment* rather than in the tests:

> **`as_posix()` is a no-op on Linux**, so deleting the separator conversion
> outright left the entire suite green. `os.sep` is already `/` here, and CI's
> Linux leg therefore cannot see the difference between a writer that
> normalises separators and one that does not — while the file the unnormalised
> writer produces opens on exactly one platform, against N-6.

The fix is the same shape the plan already chose for the different-drive
fallback, which has the same problem: the path flavour is a defaulted argument
on `_path_for_file`, and one test passes `PureWindowsPath` explicitly to assert
the conversion from a machine that is not Windows. With that in place all
eleven mutations are caught.

The general lesson is worth carrying into step 3, which owns the rest of the
path handling: **a cross-platform behaviour asserted only end-to-end is
asserted on one platform.** Anything whose whole job is to differ between
platforms needs the other platform injectable, or CI is agreeing with itself.

### What `03` cost that the plan did not expect

The plan budgeted one clarifying line in [03](../03-data-model.md). Adding
`MediaFile.missing` turned `tests/test_model.py` red immediately — it asserts
that `03`'s Entities block lists exactly the fields each dataclass has — so
`03` gained the field in its tree as well as the prose. That test doing its
job is the good outcome; the mis-estimate is that the plan filed `missing` as
a model change and the `03` line as a documentation change, when they were one
change. **A field that is never serialised is still part of the entity the
document describes.**

### Decided while writing, and small enough to stay here

- **A zero handle is absent from the file, and `handles: {}` is not the same
  as no `handles` key.** `03`'s worked example writes only `out` on the
  keyframe that opens an ease segment and only `in` on the one that closes it,
  which is what falls out of how a segment is read. Omitting zeros reproduces
  that example exactly; the empty object still distinguishes "has handles, both
  zero" from "has none", which is the model's own `Handles()` versus `None`.
- **`ensure_ascii=False`.** The format is UTF-8, and a channel called *Bläser*
  should read as one in a diff rather than as six escapes.
- **`newline="\n"` on the temporary file.** Text mode on Windows would rewrite
  every line ending, so the same project would differ by the platform that
  saved it — which is the git-friendliness in D-13 lost to a default.
- **`indent=2` explodes a handle onto four lines**, so `[24000.0, 0.0]` is
  never one line in a written file, and no output of `save()` will ever look
  like `03`'s hand-formatted example. Nothing to fix — JSON does not care, the
  plan's size measurements were taken at these settings, and the two saves
  compared for byte-identity are both this writer's. It is worth knowing
  before step 6, because it means the hand-written fixture will *not* resemble
  a saved file, which is most of why that fixture is worth typing.
- **Non-finite values are located, not just refused.** `allow_nan=False` raises
  a `ValueError` naming neither the field nor the value. One walk over the
  built document turns that into `channels[0].automation.pos.x.keyframes[1]`,
  and the document was about to be serialised anyway.
