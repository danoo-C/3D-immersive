# M3 · Phase 4 — Selection

**Status:** in progress · **Plan:**
[plans/phase_4_selection.md](plans/phase_4_selection.md)

## Goal

Clips, channels and media files can be selected: one kind at a time, as
many of that kind as wanted (D-57). Clicking, Shift+click, Ctrl+click and a
rubber band over empty lane space select clips across channels. Clicking a
header selects a channel, and a pool row is a media selection. `Ctrl+A`
selects every clip on the focused channel, then every clip in the project.
The selection lives in `core`, where every edit that takes a selection can
read it and a test can reach it without a window.

It comes before the edit verbs because every one of them acts on it (F-51).

## Scope

**In:** `core/selection.py`, the selection model planned in
[02](../02-architecture.md), observed by the UI without Qt; the three kinds
M3 has — clips, channels, media files — with keyframes left to M6; each way
of selecting in `04`'s *Selection* table; switching kind clearing the
previous kind; clearing by clicking empty space or pressing `Esc`; what
happens to a selected clip that an undo removes; the `clip selected border`
group; `B` toggling bypass on every selected channel; the pool's rows joining
the same selection rather than keeping one of their own.

**Out:** anything done to the selection → phase 5 and phase 6. The
parameters pane that follows it → phase 7. `Esc` meaning *stop* while the
transport runs → phase 9. Keyframe selection → M6.

## Acceptance

- [ ] Clicking a clip selects it alone, and Shift+click and Ctrl+click
      extend and toggle as `04`'s *Selection* table says.
- [ ] A rubber band over empty lane space selects every clip it touches,
      across channels.
- [ ] Selecting a channel clears any clip selection and the reverse, and
      selecting a pool row clears both (D-57).
- [ ] `Ctrl+A` selects every clip on the focused channel, and pressed again
      every clip in the project.
- [ ] Clicking empty space, or `Esc`, clears the selection.
- [ ] A selected clip removed by an undo leaves the selection, and nothing
      else in it changes.
- [ ] `B` toggles bypass on every selected channel as one command, and its
      tooltip no longer names M3.
- [ ] The selection is tested headless: `core/selection.py` imports no Qt,
      which `test_layering.py` already enforces for everything in `core/`.
- [ ] A selected clip is marked by the `clip selected border` group, which
      is in `04` and the bundled theme, and by more than colour alone.

## Implements

F-51, D-57 — *Selection* and *Keyboard* in
[04-ui-spec.md](../04-ui-spec.md), the planned `selection.py` in
[02-architecture.md](../02-architecture.md).

## Notes

Appended while building.
