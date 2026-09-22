# M9 · Phase 1 — Tokens and groups

**Status:** ✅ complete · **Plan:**
[plans/phase_1_tokens_and_groups.md](plans/phase_1_tokens_and_groups.md)

## Goal

`theme.py` stops being thirteen module constants and becomes a `Theme` object
carrying `tokens` and `groups`, with the QSS built from it. Nothing loads a
file yet and nothing looks different on screen — this phase is the indirection
and only the indirection, so that the phase which does load files has somewhere
to put what it loads.

## Scope

**In:** the `Theme` dataclass; the token vocabulary exactly as the palette
table in [04-ui-spec.md](../04-ui-spec.md) defines it; a first set of groups
for the widgets that exist today (window, panel, menu, toolbar, button,
splitter, scrollbar, status bar, tooltip); token-name resolution inside a
group; the QSS template reading from the object rather than from constants.

**Out:** anything to do with files → [phase 2](phase_2_file_format.md). New
groups for widgets that do not exist yet — those arrive with their widgets,
per the standing obligation in `04`.

## Acceptance

- [x] `theme.stylesheet()` returns a string **byte-identical** to the one it
      returns today. This phase changes no pixels, and that is the cheapest
      possible proof of it.
- [x] A group value that names a token resolves to that token's colour; a group
      value that is a literal `#RRGGBB` is used as-is. Both covered by tests.
- [x] A group naming a token that does not exist fails loudly **at
      construction**, not at paint time. A theme error that surfaces three
      hours later as a wrong-coloured button is the failure mode this whole
      milestone exists to prevent.
- [x] `grep -rniE '#[0-9a-f]{6}' src/immersive/ui/` finds hexes in `theme.py`
      and nowhere else, and a test asserts that so it stays true.
- [x] The existing contrast tests still pass unchanged against the object.
- [x] `channel_color(i)` keeps its signature and behaviour.

## Implements

F-44, D-46. The token vocabulary and the two-layer split are specified in the
*Theming* section of [04-ui-spec.md](../04-ui-spec.md).

## Notes

Appended while building.

### Steps 4-5 — the constants are gone, and two layers of capture

The thirteen module constants are deleted, not deprecated, and the eleven
widget call sites read `theme.color("text.primary")` instead. They read
*tokens* rather than groups, because that is how `04` specifies them: its
Icons table says `text.primary` and `text.disabled`, and its Craft section
says a panel header is `text.secondary` on `surface.raised`. Inventing group
keys for those would have been inventing vocabulary the specification did not
ask for.

**D-76 is satisfied one layer and defeated the next.** The icon tint is read
at call time, exactly as the decision requires — and `icons.icon()` is
`@cache`d, so the rendered `QIcon` from the first call answers every later
call under any theme. Both halves are right on their own and together they
rebuild the problem the decision exists to prevent. Phase 4 has to call
`icon.cache_clear()` and `app_icon.cache_clear()` when it switches; the
docstring says so and a test asserts both halves, including that the cache
*does* hold the old tint until it is cleared, because that is the part
somebody will otherwise discover by seeing a purple icon on a green theme.

### ⚠️ Six tests failed against a file that was already correct

Not a mutation, and the most useful thing this phase found.

A mutation sweep changed `"surface.raised"` from `#252526` to `#101010` and
restored it. The source was correct afterwards; the interpreter was not.
Python's bytecode cache is keyed on the source's mtime **to the second** plus
its size — and `#252526` and `#101010` are the same length, and the restore
landed inside the same second. The stale `.pyc` stayed valid, so the next run
tested the previous mutation against a file that no longer contained it.

The practice this breaks is the project's most consistent testing habit, used
in every plan since M1 phase 2, and it has been available to every sweep since.
The mutations most likely to trigger it are value-for-value swaps, which are
also the most common kind. Every sweep in the project was re-run with
`PYTHONDONTWRITEBYTECODE=1` against a purged cache: all sixty-seven mutations
across M1 phase 5 and M9 phase 1 hold, so nothing previously recorded was
wrong. The practice and the trap are now in
[09-workflow.md](../09-workflow.md), which documented neither.

**And one survivor was a sweep that was not running the right tests.** The
transport chip's two states collapsed into one and nothing failed, because the
sweep ran `test_theme.py` and `test_icons.py` and not `test_main_window.py`.
A mutation in a file no test in the run touches can only survive. **A sweep is
only as honest as the set of tests it runs**, and a survivor means nothing
until that set has been checked.

### Steps 1-3 — the vocabulary, the object, and a sheet that did not move

**`04` carried two token vocabularies for the same thirteen colours**, and
nobody had noticed because nothing had yet had to name one in code. The
palette table said `bg-1` and `accent-glow`; the `.3dimtheme` example four
sections later said `surface.panel` and `accent.text`. D-74 settles it on the
file's names, because they are what a theme author reads and edits, and phase
3 turns the built-in theme into exactly that file. `04`'s ownership table was
also missing `tab` and `focus`, both of which the sheet has styled since M0.

**Eleven groups, forty-six keys, and the count was not a coincidence:** the
sheet makes forty-six colour decisions, measured before any of this was
written. `button` matches `04`'s worked example key for key, which is the
cheapest possible evidence that the documented example is implementable.

**Naming roles costs more characters than naming colours.** Four rules went
past the line limit once `{accent_dim}` became `$button_pressed_background`,
and the byte-identical acceptance meant they could not be wrapped. The
stylesheet is now `assets/app.qss`, read through `importlib.resources` (D-30)
and substituted with `string.Template` so the file holds single braces. It
should not have been a Python string in the first place, and the plan has the
full argument.

**One mutation is equivalent rather than missed.** Replacing `value()`'s token
lookup with a fallback to the raw string survives the whole suite, and should:
construction refuses any group value that is not a literal, the reserved
`channel`, or a token that exists, so the fallback can never fire. It is
pinned by a test asserting that invariant — because it is precisely the
guarantee phase 2 has to keep when it merges a user's theme over the default,
and the day a merge produces a `Theme` without going through validation is the
day the fallback starts painting token *names* as colours, which Qt silently
drops.

**`warn` and `error` are in the vocabulary and no group uses them.** That is
correct rather than dead: clipping and missing media belong to widgets M2 and
M3 build, and load failures to the notice centre phase 4 builds. A token is a
colour a theme may set, not a colour something currently paints.
