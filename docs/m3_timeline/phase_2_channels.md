# M3 · Phase 2 — Channels

**Status:** ✅ complete · **Plan:**
[plans/phase_2_channels.md](plans/phase_2_channels.md)

## Goal

The timeline has channels. Each is a lane with a header on its left —
colour chip, name, gain, mute, solo, HRTF bypass and a snap-override
indicator, as `04` lists them. Channels can be added, removed, renamed,
reordered and recoloured. Their gain, mute, solo and bypass can be changed,
and each of those is one undoable edit. A new channel takes the next colour
of the channel palette in turn. A project opened from disk shows its
channels in their order.

## Scope

**In:** a header and a lane for each channel, in `Project.channels` order
(D-61); adding a channel, appended below the last; removing, renaming in
place, and reordering by dragging a header; recolouring from the eight
colours of the channel palette; the gain field, drag-scrubbable and typeable
with units (`04`, *Parameters pane*), built here as the shared numeric field
that phase 7 and the playhead readout reuse; mute and solo; the bypass
toggle, shown in the header (F-43); the snap-override indicator, showing
whether the channel overrides the project's snap; the `channel header`
group, and the input-field group this is the first to need; each change one
command, and a gain drag one command on release (*Undo* in
[02](../02-architecture.md)).

**Out:** clips → phase 3, including creating a channel by dropping a sample
on empty space. Selecting a channel, and `B` toggling bypass on the selected
channel → phase 4. Setting a channel's snap override → phase 5, with
snapping. What bypass does to the sound → M4. Custom colours beyond the
palette → M8, the first milestone with dialogs.

## Acceptance

- [x] Adding, removing, renaming, reordering and recolouring a channel, and
      changing its gain, mute, solo or bypass, is each one command that undoes
      exactly, and the header follows undo and redo.
- [x] A new channel takes the palette colour after the last one handed out,
      wrapping after the eighth, and a default name that says which channel
      it is. *"The last one handed out" is read as the last channel's own
      colour, so the turn is a function of the project and Undo has nothing
      else to put back — see Notes.*
- [x] Dragging a header to another place reorders `Project.channels` in one
      command, and the lanes follow.
- [x] Dragging the gain field is one command on release, however many steps
      the drag took, and a typed value with a unit — `-6 dB` — is accepted.
- [x] Solo is additive and mute wins on its own channel (D-62), and a
      channel silenced by another's solo says so in its header by an icon or
      text, not by colour alone.
- [x] Bypass is shown in the header by an icon as well as a colour (F-43),
      survives a save and a reopen, and changes nothing else about the channel
      (F-42).
- [x] A saved project reopened shows the same channels in the same order,
      with the same colours, names and states.
- [x] With more channels than fit, the wheel scrolls through them, and a
      middle-button drag pans them up and down as well as along time; the
      headers stay put sideways and follow the lanes up and down, and the
      ruler stays put up and down and follows them sideways.
- [x] `channel header` and the input-field group are in `04` and the bundled
      theme, and no widget in the timeline names a hex. *As the `channel` and
      `input` groups, styled by object name, with `timeline.separator` for
      the line between lanes.*
- [x] A screenshot of a project with channels in every state is taken and
      looked at.

## Implements

F-10, F-11, F-12, F-42, F-43 (the header), D-61, D-62 — *Timeline* and
*Channel palette* in [04-ui-spec.md](../04-ui-spec.md), `Channel` and
*Rules* in [03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**Headers are placed, not scrolled.** Each header sits at its lane's y
minus the view's own vertical scroll, and the column clips them to the
lanes' height. Two scroll areas kept in step would need matching ranges,
and the lanes have a horizontal scrollbar the headers do not. One scroll
value read by both means a header cannot label the wrong lane; five tests
scroll, wheel over the headers, pan and reorder, and check every header is
level with its lane.

**Updated in place, rebuilt only when the list changes — and compared by
identity.** A gain half-typed survives an edit to another channel. Reopening
a file gives channels *equal* to the ones on screen and not the same
objects, so a comparison by value would have kept headers that edit
channels no longer in the project. A test clicks M after a reopen.

**The next colour follows the last channel's.** "After the last one handed
out" could have meant a counter kept beside the project. It means the
palette colour after the last channel's own, so deleting a channel never
hands its neighbours one colour, and Undo has nothing extra to restore.

**Two things only looking found.** A long name was cut through a letter,
hard against the snap indicator; it now ends in an ellipsis and gives way,
with the whole name in its tooltip. And the first test written for it
measured an overlap a squeezed label never makes, so the mutation it was
for survived; the test now checks what is drawn.

**Menus are popped up, never run.** `QMenu.exec` waits for a person, and
the suite's guard reaches dialogs, not menus, so a test that reached one
would hang rather than fail. The palette and the context menu are built by
methods, opened with `popup`, and triggered directly by the tests.

**One thing to decide, not fixed here.** The timeline's default height,
set at M0 for an empty panel, shows three and a half channels in a 950 px
window. It is a splitter, so it can be dragged, but it is not remembered
until M8.

The phase adds 95 tests. The suite is 1517 tests: 12 s serially, 5 s in
parallel, 3.4 s in the fast lane.
