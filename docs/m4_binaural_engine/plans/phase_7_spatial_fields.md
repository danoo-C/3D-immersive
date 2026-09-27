# Plan — M4 · Phase 7 — The spatial fields

**Written:** 2026-09-27 · **Status:** ✅ complete

## Approach

The fields exist already, drawn with the project's values and disabled,
naming M4 or M5 (M3 phase 7). The engine takes every change they make
(phases 5 and 6), and the feed already tells the kinds apart. So this phase
turns the fields on and gives each one edit:

| Field | The edit | What the feed sends |
|---|---|---|
| Position X, Y, Z | `position`, a new `Position` with one axis changed, on each channel | a `POSITION` (D-121) |
| Pan | `pan` on each channel | a gain, four factors (D-125) |
| Distance rolloff | `rolloff` on `project.distance` | a snapshot: rolloff is structure |
| Master gain | `gain_db` on `project.master` | a `MASTER` (D-126) |
| Limiter | `limiter_on` on `project.master` | a `MASTER` |

A position edit makes a new `Position` with `dataclasses.replace`, as the
clip view makes new `Fade`s. `Position` is mutable, and one changed in place
would change what undo restores. With several channels selected, one edit
holds them all, and each keeps its own other two axes (D-127).

**What is greyed, and what shows.** Position is greyed only when every
selected channel is bypassed, and its tooltip then says why: a bypassed
channel is not placed, and its position is kept for when it is. Pan shows
only when every selected channel is bypassed, as it already does. A mixed
selection has live position fields and no pan (D-127).

**The HRTF set** stays a disabled field. It now shows the set by its title,
"SADIE II D1" from the registry rather than the id `sadie-d1`, and its
tooltip names M8 for choosing another (F-27). It is the one field in the
pane that still names a milestone.

**Tooltips.** `M4` and `M5` go from the pane. The bypass box's "heard at M4",
in the pane and in the channel header, becomes what bypass does now.

## Decisions settled here

**D-127**: with several channels selected, position is live while any is
placed and goes to all of them on the axis typed; pan shows only when all
are bypassed.

## Steps

1. **The channel's fields.** Position and pan live, the tooltips. Tests:
   - typing X is one edit that changes X alone, undo puts it back, and the
     feed sends a `POSITION`, not a snapshot;
   - several channels that differ read `—`, and a value typed there goes to
     all of them in one edit, each keeping its other axes;
   - all bypassed: position greyed and saying why, pan shown and live; a
     mixed selection: position live, pan hidden; none bypassed: pan hidden;
   - no tooltip in the pane names M4 or M5, and the header's bypass box no
     longer says "heard at M4".
2. **The project's fields.** Rolloff, master gain and the limiter live; the
   HRTF set by its title, naming M8. Tests:
   - each is one edit, undo puts it back, and the field shows it again;
   - with a window playing through a synthetic head, each is heard at the
     next block: a position typed at +X is louder on the right, a pan typed
     hard left silences the right, the master gain turns the output down,
     rolloff at 2 m changes the level by `rolloff × 6.02` dB, and the limiter
     switched off lets a hot channel past full scale.
3. **Looked at.** Offscreen grabs of the channel view with a position set,
   one channel and several, and of the project view.

## Files

`src/immersive/ui/parameters/views.py` — the fields live, D-127, the
tooltips
`src/immersive/ui/timeline/headers.py` — the bypass box's tooltip
`tests/test_parameters.py` — extended; `tests/test_fields_heard.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | a typed axis written to another | X alone changes |
| 2 | the other axes not kept (the rest set to 0) | each keeps its other axes |
| 3 | the `Position` changed in place | undo puts it back |
| 4 | several channels as several edits | one edit for all |
| 5 | position greyed when any is bypassed | a mixed selection's position is live |
| 6 | position live when all are bypassed | all bypassed: greyed |
| 7 | pan committed as the gain | a pan hard left silences the right |
| 8 | rolloff written to `min_distance` | rolloff heard |
| 9 | master gain written to each channel's gain | the master gain heard, the channels' unchanged |
| 10 | the limiter box inverted | the limiter switched off is heard |
| 11 | a project field not read back | undo shows it again |

## Risks and unknowns

- **The heard tests need a bank in the window.** Preparing one takes a
  worker and a synthetic set; `test_hrtf_in_the_window` already does it, and
  its fixture is followed here.
- **What a changed setting reaches the engine through is phase 5's and 6's.**
  Those tests hold the engine. These hold that the fields make the edits the
  feed turns into what the engine needs.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Dragging positions in the views | M5 |
| Choosing another HRTF set | M8 |
| `min_distance` and `ref_distance` in the pane | not asked for by 04; they stay in the file |

## Outcome

Built as planned, in two steps and a look. D-127 held. The named mutations
were all caught, though two by other tests than the ones named for them:

- **An axis written to another (1)** passes the one-channel test, which types
  X, the axis such a mutation gets right. The several-channels test types Y,
  and caught it.
- **The master gain written to every channel's gain (9)** cannot be heard:
  every channel 6 dB down sounds as the master 6 dB down. The pane test, which
  reads `project.master`, caught it.

The heard tests needed no new machinery: `test_hrtf_in_the_window`'s way of
preparing a stand-in set, `test_spatial`'s head, and phase 6's
`tests/hearing.py` to read the stand-in stream through the latency.

What phase 8 needs: nothing from the pane. The benchmark measures the
finished graph, 32 placed sources and the master stage, with the UI
repainting, and decides what "zero xruns" can mean on WSL (the README's
open question).
