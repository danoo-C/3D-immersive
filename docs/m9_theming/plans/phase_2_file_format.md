# Plan — M9 · Phase 2 — The `.3dimtheme` file

**Written:** 2026-09-23 · **Status:** in progress

## Approach

A new module reads a `.3dimtheme`, drops what it cannot use, merges the rest
over the built-in default and returns a `Theme` together with a structured
account of everything it dropped. It never raises. Phase 1 left `Theme`
deliberately strict — it refuses any value that is not a literal, the reserved
`channel`, or a token that exists — so the whole of this phase happens
*before* a `Theme` is constructed, and the strictness is the contract the
reader hands back to.

The alternative was to make `Theme` lenient and have it collect problems
rather than raise. It was rejected in phase 1 and is worth rejecting again
here in the same words: the built-in theme is **code**, and a group of it
naming a token that does not exist is a bug that must not ship. Two
constructors with two policies would mean the strict one is the one nobody
calls. One constructor, and a reader in front of it.

The module is `src/immersive/ui/theme_io.py`, which is the phase's first
decision and is settled below.

## Three things the phase doc does not settle

Two become rows in the decision log, taking the next free numbers, written
into [01-requirements.md](../../01-requirements.md) in step 1 along with the
high-water mark in [doc-system.md](../../doc-system.md) §3. They are not cited
by number in this plan, because a reference to an identifier that does not
exist yet is the one thing §7's dangling-reference check cannot tell from a
mistake. The third turns out not to be a decision at all.

### ⚠️ Where theme file I/O lives

[02](../../02-architecture.md)'s layout names `ui/theme.py` and nothing else.
`.3dimtheme` parsing cannot sit in `core/io/` beside `project_io.py`, because
a theme is a UI concern and N-5 keeps `core/` to the model — a rule
`tests/test_layering.py` enforces rather than merely states.

Three homes were real:

| | |
|---|---|
| **`ui/theme_io.py`** | a flat module beside `theme.py`, mirroring the `project_io.py` name the project already uses for exactly this job |
| `ui/theme/` as a package | `model.py` and `io.py` under one name, with phase 3's bundled file an obvious neighbour — at the cost of moving the module every test and eleven call sites already import |
| a top-level `immersive/theme/` | theming as its own subsystem rather than a UI detail; defensible, since `theme.py` imports no Qt — and the largest change, demanded by nothing yet |

**`ui/theme_io.py` wins**, and the argument is that it is the smallest thing
that is also the most familiar. The project already has one module whose job
is "turn a file into an object and say what was wrong with it", it is called
`project_io.py`, and a reader who has met it needs nothing explained about
`theme_io.py`. The package split buys a home for phase 3's bundled
`.3dimtheme` — but `assets/` is already that home, it is where `app.qss` and
the icons live, and it is reached through `importlib.resources` (D-30). So
the package's one advantage is not an advantage.

What this leaves open is honest: if `theme.py` and `theme_io.py` together
outgrow two files, the package split is still there, and it is a move rather
than a redesign.

### The report's shape, and whether it carries severity

`LoadResult` in `project_io.py` is the precedent: a frozen dataclass holding
the object and a list of `Problem`, each a `where` and a `message`. Reusing
`core.model.Problem` is allowed — `ui` may import `core`, only the reverse is
forbidden — and it is the wrong reuse. That type's own docstring says "one
reason a *project* is not well-formed", and its two fields cannot answer the
question phase 4 has to ask of every entry it is handed: **is this a line the
status bar shows in `warn` or in `error`?**

`04`'s *Notices* section already answers it, and already gives the vocabulary:
`error` means something the user asked for did not happen, `warn` means it
happened with a caveat. Mapped onto the failure table, the split is not
cosmetic and is not per-row arbitrary:

| Kind | Severity | Because |
|---|---|---|
| The file yields nothing — missing, unreadable, malformed JSON, not an object | `error` | somebody picked a theme and is not looking at it |
| The file yields a theme with holes — unknown key, bad colour, newer schema | `warn` | they are looking at their theme, minus one thing |
| A contrast pair below 4.5:1 | `warn` | advisory by definition; the theme loaded |

So the report carries severity, from a three-valued enum matching that table.
**It lives in `theme_io.py` for this phase and phase 4 is expected to move
it** to wherever the notice centre lands, while the only consumer is this
module. Naming that now is cheaper than discovering in phase 4 that the
notice list and the theme reader disagree about what a warning is.

The report itself is `ThemeReport`: the `Theme` — always present, always
usable — the source path, and the list. Not a `Theme` plus a bare list,
because a caller that wants to say *"VS Code Dark, with 3 problems"* should
not have to reconstruct which file it came from.

## Not a decision: a newer `schema_version` loads here and refuses in `.3dim`

These two modules are about to do visibly opposite things with the same field,
and the phase acceptance requires it: `project_io._migrated()` raises on a
file newer than it reads, and this phase's acceptance says a `schema_version`
of 2 "keeps what it recognises and says so". That looks like one of them
being wrong.

It is the code-versus-input split again, one layer out. A `.3dim` **is the
work** — opening a newer project by ignoring the parts this build does not
understand means silently discarding somebody's automation and then offering
to save over the file it came from. A `.3dimtheme` **is cosmetic**, holds
nothing that cannot be retyped, and is never written back by the application.
The worst case of a partial theme load is the wrong shade of grey; the worst
case of a partial project load is lost work.

`04`'s failure table already decided this — *"Load what we recognise, report
the rest"* — so it needs no decision row. It needs to be *said*, in the
module's docstring, next to a pointer at `project_io.py`, because the next
person to read both will otherwise reasonably conclude one is a bug.

## ⚠️ The merge rule has a consequence nobody has written down

`04`'s *Precedence* says a theme is merged over the built-in key by key, and
its failure table says an unknown token or group key is ignored and reported.
Those two lines together mean something stronger than either says alone:

> **The token vocabulary is closed.** A theme file cannot introduce a token.
> It can only give a new value to one the built-in already defines.

That is the right behaviour and it is the whole reason a partial theme keeps
working across releases — but it is a real constraint on a theme author, it is
not stated anywhere, and it produces one confusing case that the plan should
name before a test finds it:

A file defines `"my.purple": "#FF00FF"` under `tokens` and then writes
`"playhead": "my.purple"` in a group. The token is dropped as unknown. The
group value now names a token that does not exist, and falls back to the
default. **Two problems are reported for one mistake**, and neither says
"you cannot add tokens".

`project_io.py` met the same shape — a rejected field reported once by the
reader and again by `validate()` — and its answer, in `_shown()`'s docstring,
is that two true statements about one mistake are fine as long as each names
what it saw. The same answer holds, with one addition: the unknown-token
message says the vocabulary is fixed, so the second message is a consequence
the author can already explain. `04`'s *Precedence* section gains the same
sentence, because a closed vocabulary that is only discoverable by experiment
is a specification with a hole in it.

## ⚠️ The contrast rule is implemented in the test suite, and this phase needs it

`contrast()` and `_luminance()` are defined in `tests/test_theme.py`, lines
100–110. The acceptance says the loader reports every token pair below 4.5:1,
which means the rule has to exist in the package. It moves.

Where it goes matters more than it looks. The rule has **two audiences and one
implementation** — enforced against the built-in by test, advisory for a
user's theme at load — and that is the same shape as `Theme.problems()`, which
already exists and is already the model for it. So:

- `theme.py` gains `contrast(a, b) -> float`, the ratio, which is a fact about
  two colours and belongs nowhere else.
- `theme.py` gains `Theme.contrast_problems() -> list[str]`, the policy:
  which pairs, which exemptions, the 4.5:1 threshold. It sits beside
  `problems()` and reads like it.
- `theme_io.py` calls it and wraps each string as a `warn`.
- `tests/test_theme.py` asserts `BUILTIN.contrast_problems() == []` and stops
  carrying its own copy of the arithmetic.

**The exemptions have to move with it or the built-in reports itself broken.**
`text.disabled` is disabled text and `accent` is not a text colour; both are
documented in `04`'s *Accessibility and feel* and both are currently expressed
as the test's parameter list rather than as anything the code knows. A
`contrast_problems()` that rediscovers them as failures would fire on every
load of every theme including ours, which is the fastest way to teach somebody
to ignore a report.

**Scope kept narrow, deliberately.** Only the 4.5:1 text rule moves. The 3:1
rules — channel colours on `surface.panel`, `accent` as a UI component — stay
as tests over the built-in. The acceptance names 4.5:1 and only 4.5:1, and a
loader that reports a user's channel palette as insufficiently contrasty is
opinionated in a way nobody asked for. Noted here because the asymmetry is
otherwise going to read as an oversight.

## ⚠️ What phase 3 needs, and what this phase must not paint it into

Phase 3 makes the built-in theme a bundled `.3dimtheme` loaded through this
same path (D-47). There is a bootstrap problem in that sentence and it is this
phase's job to leave the door open rather than to solve it:

> This phase's reader validates a file against the built-in — the known token
> names, the known group keys, the values to fall back to. When the built-in
> *is* the file, there is nothing to validate it against and nothing to merge
> it over.

So the merge target is a **parameter**, not a hard-coded `BUILTIN`:
`load(path, over=BUILTIN)`. That alone does not solve phase 3, and pretending
otherwise here would be the mistake. What phase 3 most likely does is read its
file with no merge target at all and hand the result straight to `Theme`,
which raises — because at that moment the file is code, not input, and phase
1's split applies unchanged. That is phase 3's to decide; this phase's
obligation is to not have written `BUILTIN` into eleven places first.

## Steps

1. **The decisions, and the documents that have to agree.** Two rows in the
   decision log, the high-water mark bumped. `02`'s repo layout gains
   `theme_io.py`. `04`'s *Precedence* gains the closed-vocabulary sentence,
   and its failure table gains the two rows it is missing — a file that is
   valid JSON but not an object, and a `schema_version` that is absent or not
   a whole number. Both are cases the reader must handle and neither is in
   the table. No code.
   *Test:* the documentation invariants still hold — the high-water marks, no
   holes in any sequence, no dangling identifiers.

2. **The contrast rule moves into the package.** `contrast()` and
   `Theme.contrast_problems()` in `theme.py`; `tests/test_theme.py` imports
   the arithmetic instead of defining it.
   *Test:* the built-in has no contrast problems; a theme built with
   `text.primary` set to a near-surface grey reports exactly the pairs that
   fail and not the ones that do not; the two exemptions are still exempt, at
   the same values the test asserted before this step.

3. **The reader, and a theme that is entirely well-formed.** `theme_io.py`:
   `Severity`, `ThemeProblem`, `ThemeReport`, `SCHEMA_VERSION`, the empty
   `MIGRATIONS` table, `loads()` and `load()`. Merge over the target key by
   key, then construct.
   *Test:* a file containing only `{"schema_version": 1, "tokens": {"accent":
   "#FF0000"}}` yields the default theme with a red accent and every other
   token untouched; a group entry naming a token the file does not define but
   the default does resolves against the default; a file that sets one key of
   one group leaves that group's other keys alone.

4. **The writer, and a round trip that reads the file.** `dumps()` and
   `save()`, keys sorted, the shape `04`'s example gives.
   *Test:* a theme written and read back compares equal — **and** an
   assertion over the written text itself: the top-level keys are
   `schema_version`, `name`, `author`, `tokens`, `channels`, `groups`, they
   are sorted, and the values are the strings the theme holds. M1 phase 5
   spent three of its four survivors on this exact lesson: a round trip
   proves the reader and the writer agree, not that either is right.

5. **Every row of the failure table.** Missing file, unreadable file,
   malformed JSON, not a JSON object, unknown token key, unknown group key,
   unknown group, invalid colour value, absent `schema_version`, newer
   `schema_version`.
   *Test:* one per row, each asserting the returned `Theme` is usable and the
   report names the problem and its severity — plus one test that runs every
   row through and asserts **nothing raised**, because "none of them raises"
   is the acceptance line and a property of the set, not of any row.

6. **The contrast report, and `04`'s own example lifted out of the document.**
   Wire `contrast_problems()` into the report as advisory. Then the test M1
   phase 5 taught us to write: parse the `.3dimtheme` JSON block out of
   `04-ui-spec.md` and load it.
   *Test:* a theme whose `text.secondary` fails against two surfaces loads,
   and reports both pairs, and not one of them only; the example in the
   specification is a file this module opens.

Six steps, which is [09](../../09-workflow.md)'s stated limit rather than a
comfortable number. If step 5 grows, the split is along the seam the severity
table already marks: the whole-file failures are one step and the per-key
failures are another.

## Files

```
docs/01-requirements.md                       amended — two decision rows
docs/doc-system.md                            amended — the D high-water mark
docs/02-architecture.md                       amended — theme_io.py in the layout
docs/04-ui-spec.md                            amended — the closed vocabulary,
                                                and two rows in the failure table
docs/m9_theming/phase_2_file_format.md        amended — Notes, acceptance ticked
docs/m9_theming/README.md                     amended — phase 2 status
src/immersive/ui/theme.py                     amended — contrast(),
                                                Theme.contrast_problems()
src/immersive/ui/theme_io.py                  new — the reader, the writer,
                                                the report
tests/test_theme.py                           amended — imports the arithmetic
tests/test_theme_io.py                        new
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| `BUILTIN` hard-coded as the merge target | phase 3 cannot load the built-in through this path, which is D-47 and the milestone's acceptance | the target is a defaulted parameter from step 3, and a test loads a theme over a target that is not `BUILTIN` |
| The merge implemented shallowly | a partial theme silently loses every group it did not mention — the exact failure D-45 exists to prevent, and it looks like a working theme | named as three separate mutations below; a test sets one key of one group and asserts the group's other keys survive |
| The severity enum outliving its home | phase 4 builds a notice centre with a second, incompatible severity | three values, taken verbatim from `04`'s table, and this plan says out loud that phase 4 moves it |
| The contrast check turning into a gate | somebody's own theme refused on their own machine, which `04` explicitly forbids | the report is returned, never acted on; a mutation makes it fatal and a test must catch that |
| A round trip that never reads the file | M1 phase 5's survivor, re-armed in a new module | step 4 asserts over the text, and the mutation table below re-runs the original |
| Two reports for one mistake reading as a bug | an author who cannot tell which message to act on | the unknown-token message says the vocabulary is closed; `04` says it too |

**Mutations named in advance**, to run against the finished suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| merge order reversed — the default applied over the file | a theme file that changes nothing, and every happy-path test still passing |
| `groups` merged at the top level, the file's replacing the default's | a partial theme loses every group it did not name |
| one group merged wholesale, the file's keys replacing the default's | a theme that sets `button.background` loses the other eight button keys |
| an unknown token key kept rather than dropped | the vocabulary stops being closed, and a real token added next release collides with somebody's file |
| an unknown key dropped but not reported | the failure table row cannot be tested, and the author is told nothing |
| an invalid colour falling back to black rather than to the default's value | a theme with one typo and one black widget |
| malformed JSON raising rather than reporting | precisely what F-47 and D-48 forbid |
| a missing file raising rather than reporting | the same, by the other door |
| a newer `schema_version` refused, `project_io`-style | the acceptance line, inverted |
| an absent `schema_version` assumed to be 1 | a file with no version loads silently, and the migration hook has nothing to stand on |
| `Theme` constructed before the problems are collected | a user's typo raises, and a cosmetic file blocks startup |
| the contrast check made fatal | somebody's theme refused on their own machine |
| the contrast check reporting only the first failing pair | an author fixes one pair per attempt |
| `contrast_problems()` without the two exemptions | the built-in reports itself as broken on every load |
| severity collapsed to a single value | phase 4's status line cannot colour itself, and finds out in phase 4 |
| the writer emitting unsorted keys | every save churns the diff, which is the git-friendliness D-13 was for |
| the round trip asserting reader-against-writer only | the file's actual shape is never checked, and both can be wrong together |

The genuine unknown is **how much of `04`'s worked example is normative**.
Step 6 loads it, which settles whether it parses — it does not settle whether
`name` and `author` are required, optional, or merely present in an example.
The plan's position is that both are optional with defaults, because a
two-line theme that sets only `accent` is the property D-45 exists to
guarantee and a required `author` would break it. If step 3 finds a reason
they should be mandatory, that is a finding about the format and it belongs in
`04` rather than in this file.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Where theme files are found on disk, and the user theme directory | [phase 4](../phase_4_discovery_and_switching.md) |
| The `View > Theme` menu, and switching without a restart | phase 4 — including `icons.icon.cache_clear()`, which phase 1's Outcome flagged |
| The built-in theme becoming a bundled `.3dimtheme` | [phase 3](../phase_3_builtin_as_file.md) |
| The notice centre — anything being *shown* to a person | phase 4 (D-65). This phase returns a report; nothing displays it |
| An actual migration | nothing has been released, so there is no schema 0 to migrate from. The hook and its table exist and are empty, on `project_io.py`'s reasoning: the first real migration should not also be the redesign that introduces migrations |
| Groups for clips, waveforms, keyframes or dialogs | M2, M3, M5, M6, M8, per `04`'s ownership table |
| The 3:1 component contrast rules as a load-time report | they stay tests over the built-in; the acceptance names 4.5:1 |

## Outcome

Filled in at the end.
