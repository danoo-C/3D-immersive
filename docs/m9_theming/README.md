# M9 — Theming

Roadmap entry: [06-roadmap.md](../06-roadmap.md) · Specification: the *Theming*
section of [04-ui-spec.md](../04-ui-spec.md) · Workflow:
[09-workflow.md](../09-workflow.md)

Built after M1, numbered 9. The number is an identifier, not a position — the
roadmap's preamble says why.

| Phase | Status |
|---|---|
| [1 — Tokens and groups](phase_1_tokens_and_groups.md) | not started |
| [2 — The `.3dimtheme` file](phase_2_file_format.md) | not started |
| [3 — The built-in theme becomes a file](phase_3_builtin_as_file.md) | not started |
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
| Light mode, or any second shipped theme | Nobody asked for one. The system allows it; shipping one is a decision, not a consequence |
| Per-channel colour editing | Already F-10's channel colour, and already in the data model — themes provide the *palette*, not the assignment |
| Fonts, spacing, icon sets | Colour only. A theme that can restyle layout is a skinning engine, and that is a different project |

## Notes

Appended as phases complete.
