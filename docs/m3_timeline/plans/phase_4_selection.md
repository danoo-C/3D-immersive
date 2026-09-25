# Plan — M3 · Phase 4 — Selection

**Written:** 2026-09-26 · **Status:** in progress

## Approach

**The selection is a `core` object the document owns.** `core/selection.py`
holds one kind of thing and as many of that kind as wanted (D-57), by
identity, as the headers and the clip items already compare things. The
`Document` holds it beside the project it points into. It is cleared when
the project is replaced, and after every change the document reports, it
drops anything no longer in the project, *before* anyone is told of the
change — so nothing reading it after an Undo finds a clip that is gone.
This is recorded as a decision: `02`'s layout put `selection.py` in `core`
and said the UI observes it, but not whose it is or when it forgets.

**Every widget reads the selection and writes to it; none keeps its own.**
The timeline's clips, its headers and the pool's rows each ask the
selection whether they are selected when they draw, and each turns a click
into one call on it. The pool's tree has a selection of its own, which Qt
insists on, so the pool keeps the two in step: a change in the tree becomes
a media selection, and after every rebuild the tree is set from the
selection again.

**Clicks are decided on release where a drag might follow.** A press on an
unselected clip selects it at once. A press on a selected one leaves the
selection alone until the release, because phase 5 will drag every selected
clip from a press on any of them. A release that never moved then selects
that clip alone. This is how file managers and every DAW behave, and it is
cheaper to build now than to change the meaning of a click at phase 5.

## Decisions settled here

**The selection belongs to the document** — a decision, for the reason
above.

**Shift+click selects a range, replacing the selection.** The range runs
from the anchor — the clip last clicked or Ctrl-clicked — to the clip
clicked, and holds every clip that overlaps that stretch of time on every
lane from the anchor's to the clicked one's. Ctrl+Shift adds the range to
what is selected instead. That is the rule file managers teach, carried
across two dimensions.

**Ctrl+A's "focused channel" is the channel last clicked**, through its
header or one of its clips. With none, the first press selects every clip in
the project.

**Esc clears the selection now, and phase 9 inherits it.** The transport is
not built, so it is always stopped. `Esc` belongs to Transport › Stop, which
stays disabled until phase 9. A disabled action's shortcut does not fire,
so `Esc` reaches the window, and the window clears the selection. Phase 9's
Stop must do the same when it finds the transport already stopped.

**`B` toggles bypass on the selected channels as one edit.** If any is off,
all go on; if all are on, all go off.

## Theme keys

| Group | Key | Default | For |
|---|---|---|---|
| `clip` | `selected.border` | `accent` | a selected clip's border, 2 px — `04`'s example named it |
| `timeline` | `band` | `accent` | the rubber band's outline, over a faint fill of the same |
| `channel` | `selected.background` | `surface.hover` | a selected header |
| `channel` | `selected.marker` | `accent` | the 3 px bar down a selected header's left edge |

A selected clip and a selected header are each marked by a shape, a border
or a bar, as well as a colour.

## Steps

1. **The selection, in `core`.** `Selection` with `select`, `add`,
   `toggle`, `clear`, `prune` and `observe`; the `Document` owns one,
   clears it on New and Open, and prunes it after every change. The
   decision goes in `01`.
   *Test (headless):* one kind at a time, and switching kind clears;
   membership by identity, so two equal clips are two; an Undo that removes
   a selected clip removes it from the selection and nothing else; New and
   Open clear it; observers are told once per change and not for none.

2. **Clicking clips.** Press and release as above, Ctrl+click toggling,
   Shift+click and Ctrl+Shift+click ranges, a click on empty lane space
   clearing, and the selected border. Edit › Select All (`Ctrl+A`) with the
   focused channel, and `Esc`.
   *Test:* each way of clicking changes the selection as `04`'s table says;
   a selected clip is drawn with its border and an unselected one without;
   `Ctrl+A` twice; `Esc`.

3. **The rubber band.** A left drag starting on empty lane space draws a
   band and selects every clip it touches, across channels; with Ctrl or
   Shift it adds to what is selected.
   *Test:* a band across two lanes selects the clips it touches and no
   others; a band that touches nothing clears; with Ctrl it adds; the band
   is drawn while dragging and gone after.

4. **Channels and samples.** A click on a header selects its channel —
   plain, Ctrl and Shift as for clips — and a drag still reorders; a
   selected header is marked. `B` toggles bypass on the selected channels.
   The pool's rows are the media selection, in step both ways.
   *Test:* selecting a channel clears the clips and the reverse; selecting
   a pool row clears both and selecting a clip clears the row; `B` is one
   command over three channels, enabled only when channels are selected;
   the pool keeps its selection across a rebuild.

5. **Written down.** `04`'s *Selection* section: the range, the focused
   channel, `Esc`, what marks a selection. The new keys in its tables; the
   example's test waiting only on the fade handle and the loop region.

6. **Looked at.** A grab with clips selected on several lanes, a band being
   dragged, and a selected channel.

## Files

```
docs/01-requirements.md                     amended — a decision
docs/04-ui-spec.md                          amended — Selection, keys
docs/doc-system.md                          amended — high-water mark
src/immersive/core/selection.py             new — Qt-free
src/immersive/core/document.py              amended — owns it
src/immersive/ui/timeline/clips.py          amended — the border
src/immersive/ui/timeline/view.py           amended — clicks, band
src/immersive/ui/timeline/headers.py        amended — channel clicks
src/immersive/ui/timeline/panel.py          amended — focus, select all
src/immersive/ui/explorer/media_pool.py     amended — in step
src/immersive/ui/main_window.py             amended — Select All, Esc, B
src/immersive/assets/app.qss                amended — selected header
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — keys
tests/test_selection.py                     new — headless
tests/test_selecting.py                     new — gui
tests/test_theme_io.py                      amended — the example
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| Two selections — the pool's tree and the core — drifting | a row shown selected that nothing else thinks is | the tree is set from the core after every rebuild and every core change, with a guard so setting it does not echo back |
| A selected clip's look cached by Qt | a clip drawn unselected after being selected | selection is part of what `present` compares, so a change repaints it |
| `Esc` and `Ctrl+A` taken by a text field | the rename field's Esc cancelling the selection too, or Ctrl+A selecting clips instead of text | a line edit claims both as its own before any window action sees them; tested with the rename field open |
| A click on a header both selecting and starting a drag | a reorder that also changes the selection, or a selection that never happens | the drag decides on movement past the threshold; a release without it is a click |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| membership by equality | selecting one of two equal clips selects both |
| switching kind keeping the old kind | a clip and a channel selected at once |
| no pruning after Undo | an edit applied to a clip that is gone |
| pruning after the observers are told | a widget reading the selection during a change finds the gone clip |
| New keeping the selection | the new project arrives with the old one's clips selected |
| a press on a selected clip selecting it alone | phase 5's group drag impossible |
| Shift+click adding instead of replacing | a range that never shrinks |
| the band ignoring other lanes | a band across channels selects one |
| `B` toggling each channel separately | three channels, three different outcomes |
| the pool not reapplying after a rebuild | its selection lost on every edit |
| selected shown by colour alone | *Accessibility and feel*, broken |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Anything done to the selection — move, delete, split | phases 5 and 6 |
| The parameters pane following it | phase 7 |
| Keyframes as a kind | M6 |
| Esc stopping playback | phase 9 |

## Outcome

Filled in at the end.
