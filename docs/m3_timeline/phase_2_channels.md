# M3 · Phase 2 — Channels

**Status:** in progress · **Plan:**
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

- [ ] Adding, removing, renaming, reordering and recolouring a channel, and
      changing its gain, mute, solo or bypass, is each one command that undoes
      exactly, and the header follows undo and redo.
- [ ] A new channel takes the palette colour after the last one handed out,
      wrapping after the eighth, and a default name that says which channel
      it is.
- [ ] Dragging a header to another place reorders `Project.channels` in one
      command, and the lanes follow.
- [ ] Dragging the gain field is one command on release, however many steps
      the drag took, and a typed value with a unit — `-6 dB` — is accepted.
- [ ] Solo is additive and mute wins on its own channel (D-62), and a
      channel silenced by another's solo says so in its header by an icon or
      text, not by colour alone.
- [ ] Bypass is shown in the header by an icon as well as a colour (F-43),
      survives a save and a reopen, and changes nothing else about the channel
      (F-42).
- [ ] A saved project reopened shows the same channels in the same order,
      with the same colours, names and states.
- [ ] With more channels than fit, the wheel scrolls through them, and a
      middle-button drag pans them up and down as well as along time; the
      headers stay put sideways and follow the lanes up and down, and the
      ruler stays put up and down and follows them sideways.
- [ ] `channel header` and the input-field group are in `04` and the bundled
      theme, and no widget in the timeline names a hex.
- [ ] A screenshot of a project with channels in every state is taken and
      looked at.

## Implements

F-10, F-11, F-12, F-42, F-43 (the header), D-61, D-62 — *Timeline* and
*Channel palette* in [04-ui-spec.md](../04-ui-spec.md), `Channel` and
*Rules* in [03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
