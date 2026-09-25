# Plan — M3 · Phase 2 — Channels

**Written:** 2026-09-25 · **Status:** in progress

## Approach

Three kinds of work, each testable without the next: the edits and rules in
`core`, which need no window; the numeric field, which needs a widget but no
timeline; and the headers and lanes, which put both in front of a person.

**The headers are widgets and the lanes are drawn.** Each header is a small
`QFrame` of real controls — a colour chip, the name, the gain field, M, S and
bypass buttons, and the snap indicator — because a person types into it,
clicks it and drags it. The lanes behind the clips are painted in the view's
background, over the grid phase 1 already draws there. Nothing about a lane
is interactive until phase 3 puts clips in it.

**The headers column does not scroll; it is placed.** Every header is
positioned at its lane's y minus the view's vertical scroll value, read
straight from the view's scrollbar. Two scroll areas kept in step would need
their ranges to match, and they do not: the lanes have a horizontal
scrollbar under them and the headers do not. One scroll value, read by both,
cannot disagree — the same reasoning D-94 used for the ruler. A wheel over
the headers is handed to the view, so it scrolls what it would have scrolled
over the lanes.

```
┌────────────┬─────────────────────────────┐
│ corner     │ ruler — follows time        │
├────────────┼─────────────────────────────┤
│ headers    │ lanes — scroll both ways    │
│ follow the │                             │
│ lanes up   │                             │
│ and down   │                             │
└────────────┴─────────────────────────────┘
```

The corner holds the *Add channel* button, so it is always in reach however
far the lanes are scrolled.

**Headers are updated in place, and rebuilt only when the list changes.**
After every change the document reports, the column compares the channels it
shows with the project's, by identity. If they are the same channels in the
same order, each header re-reads its own. Otherwise the column is rebuilt.
Rebuilding on every change would destroy the name field someone is typing
into whenever anything else in the project changed.

## Decisions settled here

**A new channel's colour follows the last channel's.** It takes the palette
colour after the last channel's own, wrapping after the eighth. It falls back
to the colour in the palette at the channel count when the last channel's
colour is not in the palette at all, as with a hand-picked colour or a
different theme's palette. That makes "the colour after the last one handed
out" a function of the project, with nothing remembered beside it that Undo
would have to put back. The palette is the active theme's (D-75), passed in,
so `core` stays free of the theme.

**A new channel is named `Channel N`**, where N is one more than the count,
raised past any name already taken.

**Channel gain runs from −60 dB to +12 dB.** Below −60 is what mute is for,
and a fader that goes to −∞ puts its most-used range in its last few pixels.
`04` states the range.

**The numeric field commits once.** Dragging it scrubs the number shown, and
releasing pushes one command. Typing and pressing Enter pushes one command;
Esc puts back what was there. A value outside the range is clamped to it, and
the field shows the clamped value — that is the whole of "says so" for a
field that can only hold a number. The live audible preview of a drag belongs
to phase 8's command ring, not to a stream of undo entries.

**The chip is the channel's colour, from the project.** It is data, like the
waveform's samples, not a theme role. The reserved `channel` value is for
keys a theme might want to override on every channel, such as clip bodies at
phase 3, and the chip is not one.

## Two theme groups

Both are stylesheet groups, styled by object name, like the pool's filter.

`input` — the "input field" group that `04` lists under M8, taken here
because the gain field is the first widget to take typed input:

| Key | Default |
|---|---|
| `background` | `surface.window` |
| `text` | `text.primary` |
| `border` | `border` |
| `focus.border` | `accent` |

`channel` — the header, named for what it heads:

| Key | Default | For |
|---|---|---|
| `background` | `surface.raised` | the header |
| `border` | `border` | the line between headers |
| `name` | `text.primary` | the name |
| `quiet` | `text.disabled` | a silenced channel's name, and the snap indicator when it inherits |
| `mute.background` | `warn` | M when on |
| `mute.text` | `surface.window` | its letter |
| `solo.background` | `accent.text` | S when on |
| `solo.text` | `surface.window` | its letter |
| `bypass.background` | `text.secondary` | bypass when on |
| `bypass.text` | `surface.window` | its label |

The lanes gain one painted key, `timeline.separator` → `border`, for the
line between lanes.

Every on state carries a letter or a label as well as a colour (*Accessibility
and feel*): M, S, and a bypass button labelled `⊘ HRTF`. A channel silenced
by another's solo says *silenced* beside its name.

## Steps

1. **Channels in `core`.** A `MoveChannel` command in `core/edits.py`, and
   `new_channel(project, palette)` in `core/model.py`, which names and colours
   the next channel.
   *Test (headless):* moving a channel up, down, to either end, and onto
   itself, each undoing exactly; the colour after the last channel's, the
   wrap after the eighth, the fallback for a colour not in the palette; names
   that skip a taken `Channel N`.

2. **The numeric field.** `ui/units.py` parses and formats a quantity with a
   unit, with no Qt. `ui/widgets/numeric.py` is `NumericField`: drag to scrub
   (Shift for fine), click to type, Enter to commit, Esc to revert, clamped,
   and a `committed` signal once per gesture. The `input` group.
   *Test:* headless — `-6`, `-6dB`, `-6 dB`, `−6 dB` with a Unicode minus,
   `+3.5`, and rejects for `loud` and an empty string. With a widget — a
   typed value commits once; a drag of many steps commits once, on release;
   Esc reverts and commits nothing; out of range is clamped.

3. **Headers and lanes.** `ChannelHeader`, the `ChannelHeaders` column placed
   against the view's scroll, the corner, the lanes and their separators in
   the view, the scene as tall as its lanes, and M, S and bypass pushing one
   command each. The `channel` group and `timeline.separator`.
   *Test:* the headers follow the project's order and every change, undo
   included; M, S and bypass each push one command and follow undo; a
   channel silenced by solo says so in text; with fifteen channels, the
   wheel and a middle drag scroll the lanes, the headers stay aligned with
   their lanes, and the ruler stays aligned with the lanes sideways.

4. **Editing channels.** Add — the corner button and Edit › Add Channel;
   remove — the header's context menu; rename — a double-click on the name,
   Enter or leaving the field to keep, Esc to cancel, an empty name refused;
   recolour — the chip's menu of the palette; reorder — dragging a header,
   one `MoveChannel` on release.
   *Test:* each is one command that undoes exactly, driven through the
   widgets with synthesised events.

5. **Kept, and written down.** A project with channels in every state saved
   and reopened through the window compares equal. `04` gains the header's
   layout, the gain range and the two groups; its vocabulary table moves
   *input field* from M8 to M3.

6. **Looked at.** A grab of fifteen channels in every state, scrolled, before
   the phase is called done.

## Files

```
docs/04-ui-spec.md                          amended — header, range, groups
docs/m3_timeline/phase_2_*.md               amended — Notes, boxes
src/immersive/assets/app.qss                amended — input, channel
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — groups
src/immersive/core/edits.py                 amended — MoveChannel
src/immersive/core/model.py                 amended — new_channel
src/immersive/ui/units.py                   new — Qt-free
src/immersive/ui/widgets/numeric.py         new — NumericField
src/immersive/ui/timeline/headers.py        new — header and column
src/immersive/ui/timeline/view.py           amended — lanes
src/immersive/ui/timeline/panel.py          amended — the grid of four
src/immersive/ui/main_window.py             amended — Add Channel
tests/test_edits.py, tests/test_model.py    amended
tests/test_units.py                         new — headless
tests/test_numeric.py                       new — gui
tests/test_channels.py                      new — gui
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| Headers and lanes a pixel apart after scrolling | a header labelling the wrong lane, which is worse than no header | one scroll value read by both, and a test that scrolls and compares y positions |
| A rebuild on every change | the name field loses what is being typed when anything else changes | update in place unless the list itself changed, and a test that edits a gain while a name is being typed |
| Drag-to-scrub fighting text selection in a line edit | a field that can neither be dragged nor typed in reliably | scrub only past a threshold of a few pixels, and treat a click that never moved as a click to type |
| Synthesised drags not matching real ones | tests that pass on events no platform sends | press, a move per step, release — the shape the pan tests already use |
| Fifteen headers built per window in tests | slow GUI tests | build the panel alone, as phase 1 did, and the window only where it is the point |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| `MoveChannel` undoing to the wrong index | Undo puts a channel back one place off |
| the colour not wrapping after the eighth | a ninth channel with no colour |
| the colour counted, not following the last | deleting a channel repeats a neighbour's colour |
| a taken name reused | two channels called `Channel 3` |
| the unit required | `-6` refused where `-6 dB` is taken |
| the Unicode minus refused | a pasted `−6` rejected |
| a drag committing every step | forty undo entries for one gesture |
| Esc committing | Esc keeps what it should throw away |
| no clamp | +40 dB in the file |
| headers placed without the scroll | headers labelling the wrong lanes once scrolled |
| the column rebuilt on every change | typing lost when anything else changes |
| silenced shown by colour alone | *Accessibility and feel*, broken |
| a reorder pushing a command per step | a drag through five places, five undos |
| an empty name accepted | a channel with no name |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Selecting a channel, and `B` on the selection | phase 4 |
| Setting the snap override from the header | phase 5 |
| Clips in the lanes, and dropping a sample to make a channel | phase 3 |
| Pan, position, and what bypass does to the sound | M4 and M5 |
| Custom colours beyond the palette | M8, with dialogs |
| Track heights other than one | not planned |

## Outcome

Filled in at the end.
