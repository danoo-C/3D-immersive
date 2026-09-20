# M9 · Phase 1 — Tokens and groups

**Status:** not started · **Plan:** not written yet —
`plans/phase_1_tokens_and_groups.md`

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
