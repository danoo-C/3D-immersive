# M5 · Phase 6 — Heard

**Status:** not started · **Plan:** not written yet

## Goal

The milestone's acceptance, met the only way it can be: a person drags a
sound around the head while it plays, on headphones, and hears it move
where the drag takes it.

## Scope

**In:** a checklist, and the verdict recorded.

**Out:** anything the listening finds wrong → the phase it belongs to,
reopened, with the finding in its Notes.

## Acceptance

- [ ] **Heard**: a source dragged around the head during playback moves
      where it is dragged, with no stutter, on the listening machine.

## Implements

M5's *Done when*.

## Notes

Appended while building.

**What to listen for (prepared 2026-09-30).** Phases 1 to 5 are built. On
headphones, in the application, with a few of the stems in
`test-samples/` placed on channels and the transport playing:

1. **Drag a source slowly round the head** in the top view: left, front,
   right, behind, and back. It should be heard where the icon is, moving
   as the pointer moves, not in steps and not after the release, with no
   click or stutter.
2. **Drag it up and down** in the front view: above the head, and below
   ear level.
3. **Drag a stereo channel by its R**: the right side follows the
   pointer and the left mirrors it, both heard moving.
4. **Press Esc mid-drag**: the source goes back where it was, and is
   heard back there. Ctrl+Z after a release takes the whole drag back in
   one step.
5. **Mute, solo and bypass** from the headers: the icons fade to a
   quarter, a solo glows, and a bypassed channel leaves the canvases for
   the strip under the top view, where its ⊘ brings it back.
6. **Key 3**: the 3D tab reads the scene as the ortho views place it.

Anything heard wrong goes to the phase it belongs to, reopened, with the
finding in its Notes.

**The live count while dragging**, when the listening machine is to hand,
from the repository:

```
.venv\Scripts\python -m immersive.benchmark live --load dragging   # Windows
.venv/bin/python -m immersive.benchmark live --load dragging         # Linux
```

It drags the second of 32 moving sources round the head for a minute on
the real output, hands off, and prints the engine's xrun count, which is
this phase's line for "no stutter": 0.
