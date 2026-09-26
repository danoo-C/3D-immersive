# M3 · Phase 6 — Cut, copy and paste

**Status:** ✅ complete · **Plan:**
[plans/phase_6_cut_copy_paste.md](plans/phase_6_cut_copy_paste.md)

## Goal

`Ctrl+X`, `Ctrl+C` and `Ctrl+V` move and copy clips within a channel and
between channels (F-50). A paste lands at the playhead on the selected
channel and keeps the clips' spacing. Clips copied from several channels
paste onto that many channels, starting at the selected one. This is the
arranging gesture D-58 kept in v1: taking a phrase from one channel to
another.

## Scope

**In:** the clipboard and what it holds, as the plan decides for a paste
into a project that lacks a clip's sample; cut, copy and paste as commands,
each one undoable step; fresh ids for pasted clips; the spacing between
clips, in time and across channels, kept; a paste over existing clips
following the drop rule — the clip underneath is trimmed; Edit › Cut, Copy
and Paste enabled exactly when they can act.

**Out:** the system clipboard and other applications — nothing outside this
one reads clips. Duplicating in place → phase 5, which has `Ctrl+D`.
Copying automation along with clips → M6, if at all.

## Acceptance

- [x] Copy and then paste creates new clips with fresh ids at the playhead
      on the selected channel, keeping their spacing, and leaves the originals
      untouched.
- [x] Cut removes the selection in one command, and a paste afterwards
      brings the clips back at the playhead.
- [x] Clips copied from several channels paste onto consecutive channels
      from the selected one down, and what happens past the last channel is
      what the plan decides.
- [x] A paste over existing clips trims them so nothing overlaps, and
      `model.validate()` is clean afterwards.
- [x] One Undo removes everything one paste added.
- [x] No paste creates a clip whose `media_id` names nothing in the
      project.
- [x] Cut, Copy and Paste are enabled exactly when they can act, and their
      tooltips no longer name M3.

## Implements

F-50, D-58 — *Keyboard* and *Selection* in
[04-ui-spec.md](../04-ui-spec.md), *Ids* and *Rules* in
[03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**The clipboard is the open project's (D-99), and a paste lands on the
focused channel (D-100).** The question the milestone left here was
settled before any code. The clipboard holds copies, not the clips, so a
paste is what was copied, not what the originals have become since. The
`Document` owns it and New and Open empty it, because a clip names its
sample by an id that means nothing in another project. Carrying samples
between projects would have needed a hash rule and a fresh decode, for a
gesture F-50 describes inside one project. It can be added later without
touching the file. F-50's "selected channel" is the focused one, the one
`Ctrl+A` reads, since while clips are selected no channel is. With none, a
paste goes back to the lane it was copied from.

**Past the last lane, a paste makes channels.** Moving the paste up to fit
would overwrite channels nobody chose, and leaving clips out would lose
them without a word. A drop below the last lane already made a channel. The
channels, the clips and whatever they overwrite are one command and one
Undo. Each new channel is made against the project as it will stand with
the ones before it, or three new channels would all be *Channel 4* in
one colour.

**A resting numeric field was about to eat `Ctrl+C`.** Measured while
planning: a read-only `QLineEdit` still claims Copy, and the gain field
keeps its focus after Enter commits a value. With clips selected, the next
`Ctrl+C` would have copied "-6.0 dB". At rest the field now claims no
shortcut at all. While it is being typed into it claims what any text field
does, and both are tested. The rename field and the pool's filter keep `X`,
`C` and `V` for their text, and the pool's tree leaves them to the window.

**An id test that could only pass.** The first test of the paste's minted
ids relied on 32-bit random ids colliding, which they never do in a test
run. It now uses a random source that says everything twice. A paste that
minted a copy without looking at the copies before it, or settled each lane
with a set of its own, gives two clips one id.

**Looked at.** A kick and a hat copied from two lanes and pasted at bar 4
on Channel 3. The kick lands there and the hat on a new green Channel 4,
still a second apart and both drawn selected. The new channel sits half
below the timeline's fold, because a paste does not scroll to show itself.
The Edit menu's three verbs are greyed out in a fresh window and live after
a copy.

The phase adds 59 tests. The suite is 1776: 16.9 s serially, 6.1 s in
parallel, 3.7 s in the fast lane.
