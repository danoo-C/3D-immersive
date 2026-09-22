# M1 · Phase 5 — Project I/O

**Status:** ✅ complete · **Plan:**
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

- [x] **Round-trip equality.** A project built in code, saved and reloaded
      compares equal — the milestone's own acceptance, and the reason
      [phase 1](phase_1_dataclasses.md)'s equality had to be load-bearing.
- [x] The file is byte-identical across two saves of the same project: sorted
      keys, fixed float formatting, no timestamps (D-60). A project that
      rewrites itself differently every save is unusable in git, which is what
      D-13 was protecting.
- [x] `app_version` records the build that wrote the file and is **not**
      `schema_version` (D-60). A project that loads wrong is a bug report, and
      the writing version is the first thing anyone asks for.
- [x] Media paths are relative to the project file, and a project plus its
      audio survives being moved to another directory — and to another
      platform, which means separators are normalised on write rather than
      whatever `os.sep` happened to be (F-2, D-13).
- [x] A file whose `schema_version` is older than current loads through the
      migration hook; a file with fields the current version does not know is
      loaded, not rejected. Both have a test even though there is nothing to
      migrate yet, because the first real migration should be a function body
      and not a redesign.
- [x] A **malformed** file — bad JSON, a missing required key, a clip whose
      `offset + length` exceeds its media — fails with a report naming what is
      wrong and where, and never leaves a half-built project behind.
- [x] Missing media is reported and is **not fatal** (F-3): the clip survives,
      the `MediaFile` is marked missing, and the project loads. Relinking is
      M8's; being loadable without the audio is this phase's.
- [x] A deliberately hand-edited `.3dim` in `tests/fixtures/` loads — the
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

### Step 2 — the reader, and the milestone's acceptance

**A project built in code, saved and reloaded compares equal.** That is M1's
"done when", and it passes against a fixture built to be shaped like the
*format* rather than like music: every `Division`, `Interp` and `FadeShape`
member, all five automatable parameters, a curve with no keyframes, an
absent snap override and a present one, media inside the project directory
and media outside it, and a handle in each of the four shapes the file can
write. A separate test asserts that fixture really is exhaustive, so a grid
division added at M3 arrives with no round-trip coverage *loudly*.

**The mutation that matters most round-trips perfectly.** Swapping `out` and
`in` in the reader alone is caught by everything. Swapping them in the reader
*and* the writer together survives round-trip equality, survives save-load-save
byte-identity, and produces a file whose curves are wrong — and it is caught
only by step 1's tests, which read the file and assert the two keys by name
and by sign. That is the concrete justification for the rule step 1 was
written under: **assertions about a format belong on the file, not on the
model that came back.** Nine reader mutations were run; eight are caught.

**The ninth is outstanding by design, and is step 5's:** removing `validate()`
from `load` survives everything here, because nothing in step 2 feeds `load` a
file that `validate()` would reject. Named here so it is not mistaken for a
gap that was missed.

**Normalising a path on read is not a nicety.** Media outside the project
directory is written with `../` segments, and joining that back onto the
project directory without `normpath` yields a path with `..` still in it —
which points at the same file and is a different string, so the reloaded
project compares *unequal* and M1's acceptance fails for a reason that has
nothing to do with the format. Still not `resolve()`, for the symlink reason
the writer already had.

**Two small traps in reading numbers**, both in one place so they are not
rediscovered:

- `bool` is an `int` in Python, so `isinstance(True, int)` is true and `true`
  would quietly load into a numeric field as 1. Rejected explicitly.
- An integer field accepts a **whole-numbered** float and narrows it, because
  F-2 calls this format hand-editable and somebody typing `0.0` into a sample
  count has been unambiguous. `0.5` has not been, and is reported rather than
  truncated into a number nobody chose.

### Step 3 — paths, and a round trip's blind spot for the third time

Almost no new code: step 1 took the writer and step 2 needed the reader to
make equality work, so what was left was the fallbacks and the tests the plan
named. A project and its audio survive being moved wholesale to another
directory, a hand-typed `samples/kick.wav` resolves against the project file,
media outside the project directory round-trips through `../..`, an absolute
path in the file is read as itself, and a symlinked project directory is not
resolved through.

**Two of five path mutations survived the first sweep, and both for the same
reason:** a round trip cannot see a transformation the reader faithfully
undoes.

| Mutation | Why it round-tripped | What caught it |
|---|---|---|
| `save` resolves the project directory through a symlink | the reader joins the media path back onto the *link*, so the value comes home | the file itself, which said `../link/samples/kick.wav` where `samples/kick.wav` was meant |
| the project's directory is used without being made absolute | every test so far saved to an absolute path, where there is nothing to make absolute | saving by a relative name — `save(project, "sub/mix.3dim")` — from a different working directory |

The second is the more interesting failure, because the tests were not wrong
about the behaviour, they were wrong about the *input*: an absolute
destination is what a test naturally writes and is not what a person naturally
types. The path only came back relative — against D-71 — when the project file
was named relatively, which is an ordinary call.

That is three times in this phase that the same lesson has landed: **a round
trip proves the reader and the writer agree, not that either is right.** Step
1 found it with the handle swap, step 2 found it with the swap applied to both
sides, and step 3 found it twice in the paths. Every assertion that pins the
*format* rather than the agreement has had to read the file. Step 6's
hand-written fixture is the strongest form of that, and this phase has now
made its case three times over.

Twenty-five mutations have been named and run across the three steps.
Twenty-four are caught; the outstanding one remains `validate()` removed from
`load`, which is step 5's.

### Step 4 — version tolerance, and the half of it that needs no migration

The registry is `version -> a function returning the next version's document`,
applied one step at a time, and it is empty. A migration registered **by a
test** runs, two of them run in order, and one registered for the current
version does not run at all — which is the more damaging of the two failures,
because a hook that fires when there is nothing to do rewrites every project
on every open.

**The version is read before anything else is parsed**, and that ordering is
the whole mechanism. The test for it feeds in a file from the future whose
`channels` is deliberately not a list of channels: it is refused by version,
naming the version, rather than by a report about the garbage. A newer schema
may have changed what a field *means*, so a parse-first reader describes the
symptom while the cause is one number at the top of the file.

**The step counter is the loop's own, not the document's.** A migration that
forgets to update `schema_version` is a bug in that migration and should not
be able to express itself as an infinite loop in the loader. This is not a
hypothetical: the two-step ordering test registers migrations that never touch
`schema_version`, and it terminates because of this choice.

**The cheap half of version tolerance needs no migration at all.** A field the
file omits loads with its dataclass default — `bpm`, `snap`, `hrtf`,
`distance`, `master`, a channel's `hrtf_bypass` — which is what makes adding a
field a non-breaking change. Worth stating as guidance rather than just
behaviour: *a schema change shaped so that old files simply lack the new key
costs one default; one shaped so they lack it under a different name costs a
migration.* Prefer the first.

And `true` is an `int` in Python for the second time this phase — once in the
numeric field readers, once in the version check. Both reject it explicitly.
It is worth expecting anywhere this code asks "is this a number".

### Step 5 — failing usefully, and audio that is not there

Three kinds of outcome, deliberately kept apart, because collapsing any two
of them makes the report describe the wrong thing:

| What happened | What `load` does |
|---|---|
| The file is not a project — bad JSON, not UTF-8, not an object, a missing required key, a value of the wrong type, anything `validate()` rejects | `ProjectFileError` with **every** reason, each with its location |
| The file cannot be read at all — absent, a directory, no permission | the `OSError` the filesystem raised, unwrapped |
| The project is fine and its *audio* is not (F-3) | loads, marks the `MediaFile`, reports it in `LoadResult.problems` |

The middle row is the one worth arguing. "There is no file here" is not a fact
about the format, and wrapping it costs M3's open dialog the errno and the
standard exception type in exchange for a paraphrase.

**The phase's outstanding mutation is closed.** Removing `validate()` from
`load` survived steps 2, 3 and 4 because nothing fed `load` a file that
`validate()` would reject. A hand-written `.3dim` with two clips on top of
each other does, and it is refused naming `channels[0].clips[1]`.

### One mistake, two true reports

Writing the "every problem, not just the first" test turned up something the
plan did not anticipate: a field that is both the wrong *type* and, after
falling back to its default, an invalid *value* is reported twice — once by
the reader and once by `validate()`. A channel with `"color": 17` produces
both *color is 17, not str* and *color '' is not #RRGGBB*.

That is not duplication and it is not a bug: they are two true statements,
and suppressing the second would mean the reader deciding which of
`validate()`'s rules it has already covered, which is exactly the duplication
`validate()` exists to prevent.

It did expose a real weakness, though. **The second message describes the
fallback value, not what was typed** — `''`, not `17` — so if neither message
carried the value, someone would be sent looking for an empty string they
never wrote. The reader's messages now carry the offending value, truncated,
rather than only its type. Cheap, and it is the difference between a report
that locates a hand-edit and one that describes it.

### Step 6 — the test that reads the document, and what it found

The plan asked for a `.3dim` typed by a person rather than produced by
`save()`, because every other test in this phase round-trips the module
against itself and none of them can notice the format drifting away from what
the document describes. That fixture exists —
`tests/fixtures/handwritten.3dim`, with omitted optional fields, a `../` media
path, inline arrays and blank lines between sections — and a third test
asserts it still *looks* hand-written, so regenerating it with `save()` cannot
quietly turn the one test that is not round-tripping into one that is.

But the stronger version of the same idea is to load the listing out of
[03](../03-data-model.md) directly, and **that found something on its first
run**:

> `03`'s own worked example of the file format **was not loadable.** The
> backing mix's clip referenced `m-9e40b2d1` while the pool held only the
> kick, and `validate()` refuses a clip whose media is not in the pool.

That block is the first thing anyone implementing against this format reads.
It has been corrected in place, and the test now lifts it out of the document
and opens it on every run, so it cannot drift again. A fixture under `tests/`
is written by whoever is writing the tests and drifts with them; the example
in `03` is written for readers and is what an implementer trusts. Both are
worth having, and the document's is worth more.

**The milestone's acceptance is one test**, and every phase of M1 is in it:
phase 1's dataclasses and their equality, phase 2's curve evaluation, phase
3's snapping, phase 4's undo stack, and phase 5 carrying the result to disk
and back. Built in code, edited, undone, redone, saved, reloaded, compared
equal — with no window open and no audio device, which is N-5.

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
