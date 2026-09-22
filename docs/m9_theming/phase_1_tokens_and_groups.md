# M9 · Phase 1 — Tokens and groups

**Status:** in progress · **Plan:**
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

- [ ] `theme.stylesheet()` returns a string **byte-identical** to the one it
      returns today. This phase changes no pixels, and that is the cheapest
      possible proof of it.
- [ ] A group value that names a token resolves to that token's colour; a group
      value that is a literal `#RRGGBB` is used as-is. Both covered by tests.
- [ ] A group naming a token that does not exist fails loudly **at
      construction**, not at paint time. A theme error that surfaces three
      hours later as a wrong-coloured button is the failure mode this whole
      milestone exists to prevent.
- [ ] `grep -rniE '#[0-9a-f]{6}' src/immersive/ui/` finds hexes in `theme.py`
      and nowhere else, and a test asserts that so it stays true.
- [ ] The existing contrast tests still pass unchanged against the object.
- [ ] `channel_color(i)` keeps its signature and behaviour.

## Implements

F-44, D-46. The token vocabulary and the two-layer split are specified in the
*Theming* section of [04-ui-spec.md](../04-ui-spec.md).

## Notes

Appended while building.

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
