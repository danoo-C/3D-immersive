# M9 · Phase 3 — The built-in theme becomes a file

**Status:** not started · **Plan:** not written yet —
`plans/phase_3_builtin_as_file.md`

## Goal

The default palette stops living in Python and becomes
`assets/themes/vscode_dark.3dimtheme`, loaded at startup through exactly the
same path as a user's theme. After this phase `theme.py` contains no colours at
all — it contains the code that reads them.

This is the phase that tests the format rather than the loader: if the schema
from [phase 2](phase_2_file_format.md) cannot express the application's own
default theme, it cannot express anyone else's either, and better to find that
here than in a bug report.

## Scope

**In:** the theme file itself, under `src/immersive/assets/themes/`; loading it
with `importlib.resources` per D-30, never `__file__`; the fallback if the
bundled resource is somehow unreadable; updating the palette table in `04` to
name the file as the source of truth.

**Out:** shipping a second theme — see the milestone README. PyInstaller
packaging is verified here but owned by M8.

## Acceptance

- [ ] `grep -riE '#[0-9a-f]{6}' src/immersive/ui/theme.py` returns nothing.
- [ ] The application starts and looks **identical** to the phase 1 screenshot.
      Same proof as phase 1, same reason.
- [ ] The bundled theme loads through the phase 2 loader, not a shortcut past
      it — asserted by a test that patches the loader and sees it called.
- [ ] The file is accessed via `importlib.resources`, and a test asserts no
      `__file__` path-walking in the theme module (D-30 exists because that
      breaks under PyInstaller, which is exactly where it is hardest to debug).
- [ ] The wheel contains the theme file. `pyproject.toml` already carries an
      `artifacts` entry for the gitignored SOFA sets; themes are committed, so
      confirm they are packaged rather than assuming it.
- [ ] Contrast tests now run against the *file*, so the shipped default cannot
      drift out of the 4.5:1 rule.

## Implements

D-47, D-30. The palette table in [04-ui-spec.md](../04-ui-spec.md) remains the
specification; this phase makes the theme file its implementation, the way
`theme.py` was before.

## Notes

Appended while building.
