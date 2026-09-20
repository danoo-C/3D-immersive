# M9 · Phase 4 — Discovery and switching

**Status:** not started · **Plan:** not written yet —
`plans/phase_4_discovery_and_switching.md`

## Goal

Theme files in the user's theme directory are found, listed in a `View > Theme`
menu, and applied to the running application without a restart. The choice
survives the session. This is the phase where the previous three become
something a person can actually use.

## Scope

**In:** the platform-appropriate user theme directory and its creation on
first run; scanning it for `*.3dimtheme`; the `View > Theme` menu listing the
bundled theme and everything found; re-applying the stylesheet live; persisting
the selection with `QSettings`; showing the phase 2 report when a theme loads
with problems.

**Out:** the Preferences dialog, which is M8 and will promote this menu rather
than replace it. Hot-reload on file change — a nice trick, no one asked for it,
and it is a file watcher's worth of complexity for a file people edit twice.

## Acceptance

- [ ] A `.3dimtheme` dropped into the user theme directory appears in
      `View > Theme` after the menu is next opened, without a restart.
- [ ] Selecting a theme repaints the running application. Verified by a test
      that switches themes and asserts the applied stylesheet changed, and by a
      screenshot in the phase notes.
- [ ] A theme changing **only** the accent visibly changes the playhead and
      focus ring and nothing else. This is the milestone's own acceptance line.
- [ ] The selection persists across a restart.
- [ ] A deliberately broken theme file — the one from phase 2's tests — appears
      in the menu, is selectable, reports its problems **in the UI**, and
      leaves the application running on what it could salvage.
- [ ] The theme directory is created if missing, and an empty one is not an
      error.
- [ ] Widgets that cache colours at construction repaint. Whatever is found
      here that does not update is the first real evidence of how the
      vocabulary needs to work for M3–M6, and belongs in the Notes.

## Implements

F-48, F-47. The `View` menu is specified in
[04-ui-spec.md](../04-ui-spec.md); `QSettings` here is the same mechanism M8's
session persistence will use, chosen now so M8 adopts it rather than migrating
off something else.

## Notes

Appended while building.
