# Plan — M9 · Phase 1 — Tokens and groups

**Written:** 2026-09-22 · **Status:** ✅ complete

## Approach

`theme.py` stops being thirteen module constants and a format string, and
becomes a `Theme` object carrying `tokens`, `channels` and `groups`, with the
QSS built from it. Nothing loads a file and nothing looks different on screen.

The acceptance line that shapes the whole phase is **`stylesheet()` returns a
byte-identical string**. It is the cheapest possible proof that an indirection
changed no pixels, and it is worth saying what it costs: it means the group
vocabulary has to be able to express every colour decision the current sheet
already makes, including the ones that were written as CSS convenience rather
than as design. The mitigation is ordering — name the groups from the
ownership table in [04](../../04-ui-spec.md) first, *then* map the sheet onto
them, rather than reading the sheet and naming whatever falls out. A group
called `toolbutton_pressed_background` is a QSS selector with an underscore in
it, not a role anybody would theme.

**The indirection has to be read at call time, not captured at import.** This
is the one thing phase 1 can get wrong in a way that only phase 4 discovers.
A module constant is resolved once, when the module is first imported, so a
theme switched at runtime would repaint everything the QSS covers and nothing
that a widget baked into itself — and the eleven call sites below are exactly
that kind of baking.

## Three things the phase doc does not settle

Each is a choice between real alternatives with a consequence, so each becomes
a row in the decision log rather than a paragraph here. They take the next
three free numbers, written into [01-requirements.md](../../01-requirements.md)
in step 1 along with the high-water mark in
[doc-system.md](../../doc-system.md) §3 — they are not cited by number here,
because a reference to an identifier that does not exist yet is the one thing
§7's dangling-reference check cannot tell from a mistake.

### ⚠️ `04` carries two token vocabularies for the same thirteen colours

This is the finding that started the plan. The *Colour palette* table names
them one way and the `.3dimtheme` example in *Theming* names them another,
and both are in the same document:

| Palette table | File example |
|---|---|
| `bg-0` `bg-1` `bg-2` `bg-3` | `surface.window` `surface.panel` `surface.raised` `surface.hover` |
| `text-hi` `text-lo` `text-dim` | `text.primary` `text.secondary` `text.disabled` |
| `accent` `accent-dim` `accent-glow` | `accent` `accent.pressed` `accent.text` |
| `border` `warn` `error` | `border` `warn` `error` |

One has to win outright, and it cannot be deferred: phase 3 makes the built-in
theme a `.3dimtheme`, and from that moment the names in the file *are* the
names. Picking in phase 2 or 3 would mean renaming the vocabulary after
something already depends on it.

**The file's names win.** They are what a theme author reads, copies and
edits, and that person is the entire audience a colour name has:
`surface.panel` says what it is for, `bg-1` says where it sits in a list
nobody can see. The dotted form is already the group-value grammar in the same
example — `"hover.border": "accent.text"` — so one syntax runs through the
whole file. And `accent`, `accent.pressed`, `accent.text` group visibly in a
way `accent`, `accent-dim`, `accent-glow` do not: nothing in *dim* and *glow*
says which is darker.

Two things this does **not** cost, worth stating because both look like they
might. The monotonic surface ordering survives — it is a property of the
default theme's *values*, asserted by test, and `surface.window` through
`surface.hover` still run deepest to lightest. And no identifier is being
renumbered: token names are not `F-`, `N-`, `D-` or `QA-` identifiers, so
[doc-system.md](../../doc-system.md) §3's never-renumber rule does not apply
to them. `04`'s palette table gains the file's names, and the old ones survive
nowhere, because two names for one colour is the thing that caused this.

### The channel list is a third top-level key, not a token

`04`'s *Two layers* prose says tokens are "the thirteen in the palette table
above, **plus the channel list**". Its file example puts `"channels"` beside
`"tokens"`, not inside it. The example is right and the prose follows it.

A token is a single colour that a group value may name. The channel list is an
ordered sequence indexed by position, and `"background": "channels"` is not a
sentence — there is no colour it could mean. Folding them into one dictionary
means every consumer type-checks what it got back before it can use it, and
the one that forgets gets a list where it expected a hex, at paint time.

The reserved group value `"channel"` — *this channel's own colour* — is a
separate thing again and stays exactly as `04` describes it. Nothing in phase
1 resolves it, because no widget that exists today draws in a channel's
colour; M3 is the first, and resolving it is M3's.

### Where the active theme lives, and when its colours are read

Two real options. **Pass a `Theme` to every widget that needs one**, which is
the cleaner dependency and means threading it through `MainWindow`, the
placeholder widgets and the icon cache, plus something to tell them all when
it changes. Or **one module-level active theme, read through an accessor at
call time**, which is a global.

The global wins, and narrowly. The application has exactly one active theme by
construction — `04`'s theme picker switches the whole application, not a
panel — so the parameter being threaded would have the same value everywhere
it went, which is the definition of a global with extra steps. It also matches
what already happens: `app.py` sets one stylesheet on the `QApplication`.

What makes it safe is the second half: **the accessor reads, it does not
capture.** `theme.color("text.primary")` looks the colour up when it is
called. That is the property phase 4 needs and the only reason this is a
decision rather than a detail — a global that resolves at import time is
indistinguishable from today's constants and would push the whole problem into
phase 4 as a rewrite.

## Not a decision: failing loudly in code, leniently on a file

The phase doc's acceptance says a group naming a token that does not exist
must fail **at construction**. `04`'s *When a theme is wrong* says a theme is
never fatal and unknown keys are ignored and reported. These read as a
contradiction and are not one, and the distinction already exists in `04`
one section further down: *Contrast is checked, not enforced* holds the
built-in theme to a rule by test while letting a user's theme break it.

The same split applies here. **The built-in theme is code**, constructed in
`theme.py`, and a group of it naming a token that does not exist is a bug that
must not ship — so it raises, at construction, in a test, on the developer's
machine. **A user's theme is input**, and a typo in a cosmetic file must not
stand between somebody and their project — so it falls back and is reported.
One rule, two audiences. `04` gains a line saying so, because it took reading
two sections to work out.

## ⚠️ Measured before deciding: what the current sheet actually needs

**Forty-six colour substitutions, across eleven tokens.** Counted from the
template, not estimated:

| | |
|---|---|
| `border` | 8 |
| `text.primary` | 6 |
| `surface.raised` | 6 |
| `surface.hover` | 5 |
| `accent.pressed` | 5 |
| `surface.panel` | 4 |
| `accent` | 4 |
| `surface.window` | 3 |
| `text.disabled` | 2 |
| `text.secondary` | 2 |
| `accent.text` | 1 |

So the group layer for today's widgets is on the order of forty-odd keys, not
several hundred — which is what makes writing them out by hand reasonable, and
is the same argument D-46 makes for why groups need tokens underneath them.

**`warn` and `error` are used by no rule in the sheet.** They are real tokens
with real jobs — clipping and missing media, xruns and load failures — and
every one of those jobs belongs to a widget that does not exist yet: the
master meter is M3's and the notice centre is phase 4's. They stay in the
vocabulary, unreferenced by any group, and that is correct rather than dead:
a token is a colour a theme can set, and the notice centre in phase 4 is three
weeks from needing it.

**Eleven call sites outside the QSS already name a token**, which the phase
doc's scope does not mention and which the byte-identical acceptance does not
cover, because none of them goes through `stylesheet()`:

| File | Sites | What they colour |
|---|---|---|
| `ui/widgets/placeholder.py` | 5 | the placeholder panel body, its header and its hint |
| `ui/main_window.py` | 3 | the transport readout, the xrun counter, the version label |
| `ui/icons.py` | 3 | the normal and disabled icon tints, and the app icon |

They are the reason the accessor has to read rather than capture, and they are
in scope: the goal says the constants stop existing, and eleven references to
constants that no longer exist is not a compile error anybody should discover
in phase 4.

## ⚠️ `04`'s own ownership table is missing two of its groups

The *vocabulary grows* table says M9 owns "window, panel, menu, toolbar,
button, splitter, scrollbar, status bar, tooltip". The sheet today also styles
**the tab bar** — which exists because of D-49, the two-tab workspace — and
**the focus ring**, which `04` argues for in its own comment in the QSS and
which the *Accessibility and feel* section requires. Neither is in the row.

Both are M9's by the row's own rule, *the widgets that exist when the system
is built*. The row is corrected in step 1. Worth noticing rather than quietly
adding, because that table is the standing obligation every later milestone is
measured against, and a table with holes in it is a weaker instrument than one
without.

## ⚠️ Naming roles costs more characters than naming colours

Not anticipated, and it moved a file. Deriving each stylesheet placeholder
from its group and key — `$button_hover_border` for the `hover.border` key of
`button` — makes the names two to three times longer than the `{accent_dim}`
they replace, and four rules in the sheet went past the line limit as a
result. They could not be wrapped, because the acceptance is that the
*rendered* sheet is byte-identical and a newline in the template is a newline
in the output.

Three ways out, and the third is the only one that does not give something up:

| | |
|---|---|
| shorten the group keys | they are `04`'s, and `button` matches its worked example key for key. Shortening them to fit a Python line length is the tail wagging the dog |
| map placeholders to group keys explicitly, forty-six lines of it | reintroduces exactly the duplication the derivation removes — a table that can drift from both the sheet and the vocabulary |
| **the sheet stops being a Python string** | it never should have been one |

So `_QSS` became `src/immersive/assets/app.qss`, read through
`importlib.resources` like every other bundled resource (D-30), with
`string.Template` rather than `str.format` so the file holds single braces
and is a stylesheet an editor highlights rather than one with every `{`
doubled. The rendered output is unchanged, which the golden fixture proves.

Two things fall out that are worth having anyway. `ruff` no longer measures
the line length of another language's source — the same instinct as D-43,
which stopped it formatting Python inside Markdown. And the sheet is now
something `04`'s "no widget names a hex" rule can be asserted *on*, as a file,
which is where a hex would have been easiest to slip in and hardest to notice.

The cost is one more non-Python file that has to reach the wheel, so
`tests/test_package.py` now asserts the stylesheet and the icon set are both
reachable as resources. That is the failure D-27 exists to catch: works from
a source tree, missing from the wheel, and the application starts unstyled for
everybody who installed it rather than checked it out.

## Steps

1. **The decisions, and `04` made consistent with itself.** Three rows in the
   decision log, the high-water mark bumped. `04`'s palette table gains the
   token names it will actually carry; its ownership row gains `tab` and
   `focus`; its *When a theme is wrong* section gains the code-versus-file
   line. No code.
   *Test:* the documentation invariants still hold, and a new test asserts
   `04`'s palette table and `theme.py`'s vocabulary name exactly the same
   thirteen tokens — the same shape of test `test_model.py` uses to tie the
   Entities block to the dataclasses, and for the same reason.

2. ✅ **The `Theme` object.** A frozen dataclass of `tokens`, `channels` and
   `groups`; `color(name)` resolving a token; `group(name, key)` resolving a
   group value that is either a token name or a literal `#RRGGBB`; validation
   at construction; the module-level active theme and its accessor.
   *Test:* a group value naming a token resolves to that token's colour; a
   literal is used as-is; a group naming a token that does not exist raises at
   construction, naming the group and the key; a malformed hex raises; the
   accessor reads the *current* active theme rather than one captured when the
   module was imported.

3. ✅ **The groups, and a byte-identical stylesheet.** The forty-six
   substitutions expressed as groups, and `_QSS` reading from them.
   *Test:* `stylesheet()` equals `tests/fixtures/stylesheet_before_m9.qss`,
   captured before a line of this phase was written. Qt still parses it — the
   existing test already covers that and is the one that catches a stray `*/`.

4. ✅ **The call sites, and the last of the constants.** The eleven references
   above move onto the accessor, and the module constants are deleted rather
   than deprecated.
   *Test:* no module-level colour constant survives, asserted by inspecting
   the module rather than by grep; a widget's colour follows a change of the
   active theme, which is the assertion the constants could never have passed
   and the one phase 4 is built on.

5. ✅ **The tests that keep it true.** The contrast suite reads the object; the
   hex grep becomes a test over `src/immersive/ui/`; `channel_color(i)` keeps
   its signature and its wrapping.
   *Test:* the existing contrast expectations pass unchanged in value —
   `accent` and `text.disabled` still exempt, `accent.text` still held to
   4.5:1 — against the object rather than the constants.

Five steps. The sixth that [09](../../09-workflow.md) would allow is
deliberately unspent: if step 3 turns out to need the group vocabulary
reshaped, that is the step to split.

## Files

```
docs/01-requirements.md                        amended — three decision rows
docs/doc-system.md                             amended — the D high-water mark
docs/04-ui-spec.md                             amended — the token names in the
                                                 palette table, tab and focus in
                                                 the ownership row, and the
                                                 code-versus-file line
docs/m9_theming/phase_1_tokens_and_groups.md   amended — Notes
src/immersive/ui/theme.py                      rewritten — Theme, tokens, groups
src/immersive/ui/icons.py                      amended — three token reads
src/immersive/ui/main_window.py                amended — three token reads
src/immersive/ui/widgets/placeholder.py        amended — five token reads
tests/test_theme.py                            rewritten
tests/fixtures/stylesheet_before_m9.qss        new — the byte-identical check
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The byte-identical rule shapes the groups around the sheet's accidents | a vocabulary of QSS selectors with underscores, which no theme author would recognise | name the groups from `04`'s ownership row first, map second |
| A vocabulary invented now that M3-M6 have to fight | every later milestone bending its widgets to fit names chosen before its widgets existed | only the widgets that exist today; the rest is the standing obligation in `04` |
| The module-level theme becomes a hidden dependency | widgets that cannot be tested without global setup | the accessor takes the theme as a defaulted argument, so a test can pass one explicitly and never touch the global |
| `color()` capturing at import | phase 4 cannot switch without a restart, and finds out four phases late | a named test that swaps the active theme and asserts a call site follows |
| The golden stylesheet is regenerated rather than asserted | the phase changes pixels and says it did not | it is a *migration* check with a stated expiry: it retires when a milestone legitimately changes a colour, in a commit that says which and why |

**Mutations named in advance**, to run against the finished suite:

| | |
|---|---|
| the golden stylesheet regenerated instead of asserted | the phase changes pixels silently |
| a group value always treated as a literal | a theme that cannot retint anything |
| a group value always treated as a token name | a literal `#RRGGBB` escape hatch that does not work |
| a missing token resolved to a default instead of raising | a wrong-coloured widget discovered three hours later |
| a malformed hex accepted at construction | Qt silently drops the rule and the widget renders unstyled |
| `color()` resolving against a theme captured at import | phase 4 cannot switch |
| the channel list folded into `tokens` | a group value naming it type-errors at paint time |
| `channel_color` losing its wrap | the ninth channel has no colour |
| the vocabulary test comparing against a list written in the test | `04` and the code drift, which is what the test is for |
| a call site left on a constant | a widget that does not follow a theme switch |
| the contrast suite left pointed at the old constants | the rule stops being checked while still appearing to be |

The genuine unknown is **whether `groups` is nested or flat** — `{"button":
{"hover.border": ...}}` against `{"button.hover.border": ...}`. `04`'s example
is nested and phase 1 follows it, because the example is the specification and
a format is not the place to be clever. If phase 2 finds that merging a user's
partial theme over the default is materially harder one way than the other,
that is a phase 2 finding about merging and the shape can change then, while
the only consumer is still this module.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Reading or writing a `.3dimtheme` | [phase 2](../phase_2_file_format.md) |
| The built-in theme becoming a bundled file | [phase 3](../phase_3_builtin_as_file.md) |
| Discovery, the `View > Theme` menu, switching without a restart | [phase 4](../phase_4_discovery_and_switching.md) |
| The notice centre, and anything being *reported* to a person | phase 4 — it builds the surface (D-65). Phase 1 raises, which is a developer's report |
| Groups for clips, waveforms, keyframes, spatial views or dialogs | M2, M3, M5, M6 and M8, per the ownership table in `04` |
| Light mode, or any second theme | nobody asked for one; M9 makes it possible, not present |
| Fonts, spacing, icon *sets* | colour only. A theme that restyles layout is a skinning engine |

⚠️ **One thing phase 2 will need that no document currently provides:** a home
for theme file I/O. [02](../../02-architecture.md)'s repo layout names
`ui/theme.py` and nothing else, and `.3dimtheme` parsing cannot go in
`core/io/` beside `project_io.py`, because a theme is a UI concern and N-5
keeps `core/` free of anything that is not the model. Flagged here rather than
settled, because phase 1 does not need it and phase 2 cannot start without it.

## Outcome

Five steps, in order, and `stylesheet()` returns the bytes it returned before
any of it. The three decisions went in as D-74, D-75 and D-76 and none needed
revisiting once code depended on them.

### What the plan got wrong

**It assumed the stylesheet stayed a Python string.** Naming roles costs more
characters than naming colours, four rules went past the line limit, and the
byte-identical acceptance meant they could not be wrapped. The sheet is now
`assets/app.qss`, and the full argument is in the amendment above. The plan
was not wrong about the work, it was wrong about where the work lived.

**Step 4 and step 5 were one step.** Deleting the module constants breaks
every test that reads one, so porting the contrast suite onto the object was
not a separate thing that could follow — it was the same commit. The split
looked real when the plan was written because the constants looked like a
source concern and the contrast suite like a test concern; they were one
dependency.

**The `@cache` on the icon set was not anticipated at all**, and it is the
more interesting miss. D-76 is satisfied — the tint is *read* at call time —
and the rendered `QIcon` is then memoised against its arguments, so the first
call under one theme answers every later call under any other. Reading at call
time and caching the result are both right and together they reintroduce the
exact problem D-76 exists to prevent, one layer up. Phase 4 has to call
`cache_clear()`, the docstring now says so, and a test asserts both halves.

### Which mutations survived the first suite

Thirty named across the phase. Three survived a first run:

| Survivor | What it was |
|---|---|
| a group value falling back to itself rather than raising | **equivalent** — construction refuses any value that is not a literal, the reserved `channel`, or a token that exists, so the fallback cannot fire. Pinned by a test asserting that invariant, because it is the guarantee phase 2 has to keep |
| the icon tint pinned to the built-in theme | a missing test, and the one that found the `@cache` problem |
| the transport chip's two states collapsed | a missing test — and a sweep that was not running the file the test would live in |

The third is worth its own line, because the fix was not a test. The sweep ran
`test_theme.py` and `test_icons.py` and not `test_main_window.py`, so a
mutation in the window could only ever survive. **A mutation sweep is only as
honest as the set of tests it runs**, and a survivor is meaningless until you
have checked the suite it survived was the right one.

### ⚠️ And one that was not a mutation at all

Six tests failed against a source file that was already correct. The cause was
`__pycache__`: `#252526` and `#101010` are the same length, the restore landed
in the same second, and Python's bytecode cache — keyed on mtime to the second
plus size — considered the stale `.pyc` valid. The interpreter was running the
previous mutation against a file that no longer contained it.

This is a flaw in the *practice*, not in this phase, and it has been available
to every sweep since M1 phase 2. Most mutations change length enough to be
safe; the ones that do not are exactly the value-for-value swaps, which are
the most common kind. Every sweep in the project was re-run with
`PYTHONDONTWRITEBYTECODE=1` and a purged cache, and all sixty-eight mutations
across M1 phase 5 and M9 phase 1 hold — so nothing previously recorded was
wrong. The practice and the trap are now written into
[09-workflow.md](../../09-workflow.md), which owned neither.

### What phase 2 inherits

**The token vocabulary held up**, and the strongest evidence is small: the
`button` group matches `04`'s worked example key for key, which means the
example in the specification is literally what the code contains. Phase 2 is
the first thing other than this module to read those names, and it starts from
a document and an implementation that already agree.

**A reader that must not use `Theme`'s constructor to validate.** This module
raises, deliberately, because the built-in theme is code. A user's file cannot
be allowed to. Phase 2 drops what it cannot use, reports it, merges what is
left over the default, and hands `Theme` something already known to be
well-formed — and the invariant test above is what says that is still true.

**Nowhere to put the parser.** [02](../../02-architecture.md)'s layout gained
`assets/app.qss` in this phase and still names no module for theme file I/O.
It cannot sit in `core/io/` beside `project_io.py`, because a theme is a UI
concern and N-5 keeps `core/` to the model. That is phase 2's first decision
and it is unmade.
