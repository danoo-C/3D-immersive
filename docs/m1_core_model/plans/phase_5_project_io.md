# Plan — M1 · Phase 5 — Project I/O

**Written:** 2026-09-21 · **Status:** in progress

## Approach

`core/io/project_io.py`: a `save(project, path)` and a `load(path)` that are
inverses, plus a `schema_version` and a migration hook with nothing to migrate
yet. This closes the milestone — *built in code, edited, undone, saved,
reloaded and compared equal* — and it is the first module that touches the
filesystem at all.

**The schema is written by hand, not derived.** `dataclasses.asdict()` plus
reflection over type hints would be shorter and is the obvious first idea. It
does not survive contact with the schema in
[03-data-model.md](../../03-data-model.md), which diverges from the
dataclasses in four places that reflection cannot guess:

| In the model | In the file | Why |
|---|---|---|
| `Handles.outgoing` / `.incoming` | `handles: { out, in }`, either key absent | `in` is a Python keyword; `03` uses the short names and `curves.py` already says this module maps them back |
| `time_signature: tuple[int, int]` | `[num, den]` | JSON has no tuple, and a list read back as a list breaks round-trip equality |
| `Interp`, `FadeShape`, `Division` | `"ease"`, `"equal_power"`, `"1/16"` | `StrEnum` serialises as a string for free but has to be reconstructed deliberately |
| `MediaFile.missing` | *nothing* | derived from the filesystem at load; writing it would make the file depend on which machine saved it |

A derived writer would need four exceptions anyway, and an exception in a
reflective writer is harder to read than the whole explicit one. The explicit
version also fails loudly when the model gains a field and nobody updated the
schema, which is the failure you want.

**`validate()` is the gate at both ends.** A project that `validate()` rejects
is not written, and a file that produces one is not opened. That is the same
rule [phase 4](../phase_4_undo_stack.md) applies to every edit, and it is what
lets each end trust the other: the stack can assume a loaded project is
well-formed, and `load` can assume anything on disk was well-formed when it
was written. Harsh for a hand-edited file with one overlapping clip — but the
report names what and where, and opening a project the undo stack guarantees
cannot exist is worse than refusing with an explanation.

## Three things the phase doc does not settle

Each is a choice between real alternatives with a consequence, so each becomes
a row in the decision log rather than a paragraph here. They take the next
three free numbers, written into
[01-requirements.md](../../01-requirements.md) in step 1 along with the
high-water mark in [doc-system.md](../../doc-system.md) §3 — they are not cited
by number in this plan because a reference to an identifier that does not exist
yet is the one thing §7's dangling-reference check cannot tell from a mistake.

### Media paths are absolute in memory and relative on disk

`03`'s Entities block says `MediaFile.path` is "relative to the project file",
and the whole of that block is describing what is in a `.3dim`. Read as a
statement about *memory* it has a hole in it: a new project that has never been
saved has no project file for anything to be relative to, so every path in the
media pool would be relative to nothing until the first `Ctrl+S`.

So the relativity is a property of serialisation. In memory a `MediaFile.path`
is absolute and M2 can open it; `save` makes it relative to the project file's
directory and `load` makes it absolute again. `03` gains a line saying which
of the two it is describing.

The fallback matters as much as the rule: media that is not under the project's
directory produces `../..` segments, which is fine, and media on a different
Windows drive produces no relative path at all, where `os.path.relpath` raises.
That case writes the absolute path and the project stops being portable —
which is the truth about that project, and better than a save that fails.

### Missing media is a field on `MediaFile`, excluded from equality

F-3 wants the clip to survive and be greyed, which means something has to carry
"this file was not there". The two candidates are a field on `MediaFile` and a
list of ids on the load result. A list is cleaner until the UI needs it, at
which point every clip-drawing routine is doing a lookup against a list it had
to be handed.

The field is `missing: bool`, defaulted `False`, **never serialised**, and
**`compare=False`**. Excluding it from equality is not a convenience for the
round-trip test: two projects that differ only in whether their audio is
currently plugged in are the same project, and equality that says otherwise
would make the milestone's acceptance depend on what happens to be on disk.

### Fields the current version does not understand are dropped

A file written by a future build can carry keys this one has never heard of.
Preserving them across a round-trip is the friendlier behaviour and is what
stops an older build silently deleting a newer one's work. It also means the
model carries a bag of untyped data that `validate()` cannot check, that the
undo stack cannot edit, and that a hand-edit can fill with anything.

They are dropped, and the cost is stated rather than hidden: opening a newer
project in an older build and saving it loses whatever the newer build added.
At schema 1 there is nothing to lose. If that changes the answer can change
with it — which is the argument for writing the trade-off down now, while it
is free.

## ⚠️ Measured before deciding: what the file format actually costs

Three questions the acceptance leans on, answered with numbers.

**Are floats byte-stable across a save/load/save?** Yes. 200 000 random
doubles, dumped, parsed and dumped again: zero differ. Python's float `repr`
is shortest-round-trip, so `sort_keys=True` is the only other thing
byte-identical saves need.

Two traps that go with it. `json.dumps` writes `NaN` and `Infinity` by
default, which are **not valid JSON** and which other tools reject — so
`allow_nan=False`, and a non-finite value becomes a reported problem rather
than a file nobody else can read. And an `int` where the schema shows a float
writes as `0` rather than `0.0`; it round-trips and compares equal, but it
does not match the documented schema, so numbers are coerced on write.

**What does a project weigh?** `indent=2` and sorted keys, measured against a
synthetic project at three scales:

| | clips | keyframes | file | write | read |
|---|---|---|---|---|---|
| N-4's scale | 96 | 320 | 152 KiB | 2.5 ms | 0.7 ms |
| busy | 960 | 2 880 | 1.3 MiB | 33 ms | 7.9 ms |
| large | 6 400 | 15 360 | 7.6 MiB | 200 ms | 47 ms |

Automation dominates, not clips: a keyframe with handles is five numbers and a
clip is seven, but there are far more keyframes. Nothing here is a problem for
an explicit `Ctrl+S`, and the write timings are an upper bound because they
were taken through `dataclasses.asdict`, which deep-copies everything first.

**What does pretty-printing cost?** Two to three times the bytes — 39.6 KiB
against 19.7 compact without automation, 152.5 against 53.5 with it. At these
sizes that buys a file that `git diff` can show a one-line change in, which is
what D-13 was for, and it is not close.

## ⚠️ Step 1 took the writer's half of step 3

Step 3 owns paths — *relative on write, absolute on read*. The write half
turned out to belong here: `save()` cannot put a path in a file without
deciding which of the two forms it takes, and D-71, written in this same step,
says relative. A `save()` that wrote absolute paths for two more steps would
have been knowingly wrong against a decision made in the same commit, and
step 3 would then have been a rewrite rather than an addition.

So `_path_for_file`, the off-tree `../..` case and the different-drive
fallback are in step 1. Step 3 keeps the reader, the moved-project round trip,
and the fallback tests it names — it is smaller than planned, not larger.

## ⚠️ `03` gained a field, not only a line

The plan expected one clarifying line in [03](../../03-data-model.md) about
path relativity. It needed two changes, because `tests/test_model.py` asserts
that `03`'s Entities block lists exactly the fields the dataclasses have —
and that test went red the moment `MediaFile.missing` was added, which is
precisely what it is for. So the Entities tree gained `missing` beside the
prose note, and the *Files* table below is amended to say so.

Worth recording rather than fixing quietly: the plan treated `missing` as a
model change and `03` as a documentation change, and they are the same change.
A field that is never serialised is still part of the entity the document
describes.

## ⚠️ The reader collects problems rather than raising on the first

Not in the plan, and it changes the shape of step 5 rather than its content.
Every `_read_*` function needs somewhere to record "this key is the wrong
type" and the location it was at, and threading a list and a path through
twenty functions is the kind of noise that gets dropped at one call site and
noticed by nobody. So there is a small `_Reading` object holding the problem
list, passed down once.

The consequence is that reading is **lenient while it runs and fatal at the
end**: a bad field is recorded, replaced by its default, and the pass carries
on to find the rest. Whether any of it is fatal is decided once, by `load`.
That is `validate()`'s own rule — somebody reporting a bad file wants the
list, not the first line of it — and it means step 5 inherits a reader that
already reports what and where, and has to add the file-level failures rather
than retrofit locations into twenty functions.

## Steps

1. ✅ **The decisions, then the writer.** Three rows in the decision log, the
   high-water mark bumped, the one clarifying line in `03`. Then `to_dict` per
   entity and `save()`: `sort_keys=True`, `indent=2`, `allow_nan=False`, UTF-8,
   a trailing newline, and an atomic write — a temporary file in the same
   directory and `os.replace`, so a crash mid-save cannot truncate the project
   that was already there.
   *Test:* two saves of the same project are byte-identical; `app_version`
   is present, is `immersive.__version__`, and is not `schema_version`; no key
   anywhere holds a timestamp.

2. ✅ **The reader, and round-trip equality.** `from_dict` per entity, `load()`
   returning a `LoadResult(project, problems)`.
   *Test:* the milestone's own acceptance — a project exercising every field,
   every `StrEnum` member, an absent `snap_override`, an empty `automation`,
   both handle keys and neither, saved and reloaded, compares equal. Then
   save-load-save is byte-identical, which is the assertion that catches a
   reader and writer that are both wrong in the same direction.

3. ✅ **Paths.** Relative on write, absolute on read, `/` on both regardless of
   `os.sep`; the off-tree and different-drive fallbacks.
   *Test:* a project and its audio moved wholesale to another directory still
   resolve. A file containing `samples/kick.wav` loads to the right absolute
   path whatever the platform separator is. Symlinked project directories are
   not resolved through, so a project inside one keeps the path the user typed.

4. ✅ **Version tolerance and the migration hook.** `SCHEMA_VERSION`, a registry
   of `from_version -> callable` applied in order, a file from the future
   refused by version rather than by a confusing parse error.
   *Test:* a migration registered **by the test** runs and its output is what
   gets parsed — the hook has nothing real to do yet, so the only way to know
   it works is to give it something. A file missing a field the current version
   knows loads with the default; a file carrying a field it does not know loads
   without it.

5. ✅ **Failure, and missing media.** `ProjectFileError` carrying `Problem`s for
   anything that means there is no project here — bad JSON, a missing required
   key, a value of the wrong type, and anything `validate()` rejects. Missing
   media is not that: the `MediaFile` is marked, the clip survives, the project
   loads and the problem is reported.
   *Test:* each failure names what and where and leaves no half-built project.
   A project whose audio has been deleted still loads, and the one whose file
   is gone is the one marked.

6. **A hand-written fixture, and the milestone end to end.**
   `tests/fixtures/handwritten.3dim`, typed by a person rather than produced by
   `save()`.
   *Test:* it loads, and what it loads is what it says. This is the only test
   that can catch the schema drifting away from what someone reading
   [03](../../03-data-model.md) would reasonably type, because every other test
   here is round-tripping this module against itself. Then the milestone's
   acceptance in one test: build in code, edit through the undo stack, undo,
   save, reload, compare equal.

Six steps, which is [09](../../09-workflow.md)'s limit — and a sign this phase
is at the top of its size. If step 4 or 6 grows while building, it splits out
rather than swallowing the rest.

## Files

```
src/immersive/core/io/project_io.py   new — save, load, the schema, migration
src/immersive/core/model.py           amended — MediaFile.missing
tests/test_project_io.py              new
tests/fixtures/handwritten.3dim       new — typed by hand, deliberately
docs/01-requirements.md               amended — three decision rows
docs/doc-system.md                    amended — the D high-water mark
docs/03-data-model.md                 amended — path relativity, and `missing`
                                        in the Entities tree
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A test asserts a mechanism without distinguishing it | The phase 2 failure, a third time | Mutations named now, run against the finished suite — the list is below |
| Writer and reader are wrong in the same direction | Round-trip equality passes and the file is not the documented schema | The hand-written fixture in step 6, which is the only test not round-tripping this module against itself |
| `validate()` refusing to open a hand-edited file | Someone's edit locks them out of their project | The report names what and where; refusing is deliberate, and argued above |
| Non-finite floats | A file that Python writes and nothing else can read | `allow_nan=False`, reported as a problem |
| `os.path.relpath` raising across Windows drives | A save that fails instead of a project that is merely not portable | Fall back to an absolute path; tested by simulating the raise, since CI is Linux |
| Symlinked project directories | Paths silently rewritten to somewhere the user never typed | Absolute-and-normalised, never `resolve()`d |
| The migration hook is never exercised | The first real migration becomes a redesign | Step 4 registers one from the test |

**Mutations named in advance**, to run against the finished suite:

| | |
|---|---|
| `sort_keys` dropped | two saves differ |
| `time_signature` left a list on read | round-trip equality |
| `handles` `in` and `out` swapped | a curve that evaluates differently after a reload |
| a `StrEnum` written by `repr` rather than `.value` | `"Interp.EASE"` in the file |
| the relative path computed against the working directory | a project that only opens from where it was saved |
| separators left as `os.sep` on write | a file that loads on one platform |
| `missing` included in equality, or serialised | round-trip depends on what is on disk |
| the migration hook skipped when the version already matches | a registered migration never runs |
| an unknown field raising instead of being dropped | a future file refused |
| `validate()` not run on load | a file that opens into a project phase 4 guarantees cannot exist |
| the save written in place rather than through `os.replace` | a crash mid-save truncates the project that was there |

The genuine unknown is **whether `MediaFile.missing` stays on the model**. It
is the first derived, machine-local fact to live on a model dataclass, and if
M2 finds it wants a richer answer than a bool — resolved, missing, wrong
length, wrong hash — then the field becomes a small enum or moves out to a
resolution table, and the decision row is superseded rather than edited. That
would be an M2 discovery about media resolution, not about this format, and
nothing in the file changes either way, because it is never written.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The relink dialog for missing media (F-3) | M8 — this phase reports it as data and resolves nothing |
| Decoding, resampling or hashing anything the paths point at | M2. `hash` is stored and compared, never computed here |
| Autosave and the recovery sidecar (F-49, D-64) | M8, and it writes a sidecar rather than the project |
| The notice surface that shows a load problem (F-56, D-65) | M9. `load` returns its problems; something later displays them |
| `.3dimtheme` | M9 — a different file with a different schema, which inherits this migration discipline |
| Open, save, save-as as *menu actions* (F-1) | M3, when there is a window to hang them on. This phase is the two functions they will call |
| A real migration | The first time `SCHEMA_VERSION` goes to 2 |

## Outcome

Filled in at the end. What actually happened, what this plan got wrong, which
mutations survived the first suite, and what M2 inherits — in particular
whether `MediaFile.missing` held up and what the hand-written fixture caught.
