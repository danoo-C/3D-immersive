# M9 — Theming

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Specification: the *Theming*
section of [04-ui-spec.md](../04-ui-spec.md) · Workflow:
[09-workflow.md](../09-workflow.md)

Built after M1, numbered 9. The number is an identifier, not a position — the
roadmap's preamble says why.

| Phase | Status |
|---|---|
| [1 — Tokens and groups](phase_1_tokens_and_groups.md) | ✅ |
| [2 — The `.3dimtheme` file](phase_2_file_format.md) | ✅ |
| [3 — The built-in theme becomes a file](phase_3_builtin_as_file.md) | ✅ |
| [4 — Discovery and switching](phase_4_discovery_and_switching.md) | not started |

The order is deliberate and each phase is useless before the one above it:
you cannot load a theme file into constants (1 before 2), you cannot prove the
format expresses the default until the default is written in it (2 before 3),
and there is nothing to switch between until there are two themes (3 before 4).

## Milestone acceptance

Copied verbatim from the roadmap's "Done when":

> the application's entire palette lives in a bundled `.3dimtheme`, a user theme
> file that changes only the accent visibly works, and a deliberately broken
> theme file is reported without preventing startup.

## What this milestone does not deliver

| Not here | Where |
|---|---|
| A complete token vocabulary | Impossible now — the widgets for M3–M6 do not exist. Each milestone adds its own groups to `04` as it builds them |
| The Preferences dialog | M8. M9 ships a `View > Theme` menu, which M8 promotes |
| Per-notice actions — relink, reveal, choose device | M8. M9 builds the notice surface itself, because phase 4 cannot pass without one (D-65) |
| Light mode, or any second shipped theme | Nobody asked for one. The system allows it; shipping one is a decision, not a consequence |
| Per-channel colour editing | Already F-10's channel colour, and already in the data model — themes provide the *palette*, not the assignment |
| Fonts, spacing, icon sets | Colour only. A theme that can restyle layout is a skinning engine, and that is a different project |

## Notes

Appended as phases complete.

**Phase 1.** `theme.py` carries a `Theme` — thirteen tokens, eight channel
colours, eleven groups, forty-six group keys — and the stylesheet is built
from it without a single pixel moving. Three decisions came out of it: one
token vocabulary rather than the two `04` was carrying (D-74), the channel
list as a third top-level key rather than a token (D-75), and one active theme
read through an accessor that resolves at call time rather than at import
(D-76). `04` also gained the two groups its own ownership table was missing,
`tab` and `focus`.

The stylesheet moved out of Python into `assets/app.qss`, because naming roles
costs more characters than naming colours and four rules would not fit a line.
It should not have been a Python string in the first place.

Two things phase 2 starts from. The `button` group matches `04`'s worked
example key for key, so the specification's example is literally what the code
holds — which is the cheapest evidence the vocabulary is usable by something
other than the module that invented it. And `Theme` raises on anything
malformed, deliberately, so phase 2 has to drop and report *before* it
constructs one: the strictness is the contract, not an obstacle to it.

Still unmade, and phase 2's first decision: [02](../02-architecture.md) names
no module for theme file I/O, and it cannot go in `core/io/` beside
`project_io.py`, because a theme is a UI concern and N-5 keeps `core/` to the
model.

**Phase 2.** `theme_io.py` reads a `.3dimtheme`, merges it over a target
theme and reports what it dropped, and nothing in it raises. Two decisions:
the module's home (D-77) and a report whose entries carry a severity taken
from `04`'s *Notices* vocabulary (D-78). `04` gained three things it was
missing — the closed token vocabulary, the wholesale channel merge, and two
rows in its failure table.

The phase found that a five-line theme file could stop the application
starting: `"channel"` is a value `04` documents, `Theme` accepts it, and
`stylesheet()` then raises on it. A theme can be well-formed and still be one
the application cannot paint with. The battery that asserts nothing raises
now builds a stylesheet from every theme it produces.

Phase 3 starts from a reader whose merge target is already a parameter, and
from the one thing that is still unsolved: when the built-in *is* the file,
there is nothing to merge it over.

**Phase 3.** The palette is `assets/themes/vscode_dark.3dimtheme` and
`theme.py` holds no colour at all — it holds the code that reads them. The
bootstrap phase 2 handed over dissolved: nothing can validate the built-in
against an external vocabulary, and nothing needed to, because `Theme`,
`stylesheet()` and `contrast_problems()` already cover it between them. Two
decisions: no fallback palette (D-79) and a cached `builtin()` reached
through a deferred import, because `theme_io` already imports `theme` (D-80).

The migration was deliberately two steps, so the file could be proved equal
to the constants while the constants still existed. The proof that no pixel
moved was phase 1's golden stylesheet fixture, untouched and still matching.

Of fifteen mutations, four survived a first run and three were real: D-30 was
asserted for `theme.py` and not for `theme_io.py`, the bundled theme's
encoding was explicit but untested, and D-80's second half had no test at
all.
