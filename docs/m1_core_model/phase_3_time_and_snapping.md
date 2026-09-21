# M1 · Phase 3 — Time and snapping

**Status:** ✅ complete · **Plan:**
[plans/phase_3_time_and_snapping.md](plans/phase_3_time_and_snapping.md)

## Goal

`core/time.py` converts between the three ways this application talks about
time — samples, seconds, bars:beats — and snaps a sample position to the grid
or to a neighbouring clip edge. Samples stay the single source of truth; the
other two are views (D-11, and the *Time* section of
[03-data-model.md](../03-data-model.md)).

## Scope

**In:** samples ↔ seconds; samples ↔ bars:beats:ticks from `bpm` and
`time_signature`; snap divisions 1/1 through 1/32 plus triplets and "off"
(F-16); snapping to the grid **and** to other clips' edges (F-17); the
per-channel override, including disabling it (F-18).

**Out:** the ruler and its bars:beats ↔ min:sec toggle → M3, which displays
what this computes. Holding `Alt` to bypass snap → M3; it is an input gesture,
and this phase provides the "off" it resolves to. Tempo maps → never (D-26).

## Acceptance

- [x] Round-trip: samples → bars:beats → samples is **exact** for every
      position on the grid, and off it the error never exceeds **half a tick
      plus half a sample**. Everything downstream assumes this and nothing else
      checks it.
- [x] Every division from 1/1 to 1/32 and every triplet variant produces the
      grid spacing it claims, at 4/4 and at one other time signature. A
      division that is silently wrong is an arrangement that will not line up,
      discovered by ear three milestones later.
- [x] Snapping picks the **nearest** candidate among the grid and the clip
      edges in range, not the nearest grid line with clip edges as an
      afterthought (F-17). Asserted with a clip edge deliberately placed just
      inside a grid line.
- [x] A channel's `snap_override` wins over `Project.snap`, including when it
      disables snapping entirely (F-18); `null` inherits.
- [x] Snapping is idempotent: snapping an already-snapped position returns it
      unchanged. A snap that drifts on repeated application will move clips
      that nobody dragged.
- [x] **Changing the BPM moves the grid and not the material** (D-52).
      Asserted directly: build an arrangement, change `bpm`, and every clip
      `start` and every keyframe `t` is unchanged while their bars:beats
      readings are not. This is the surprising behaviour in the whole model,
      so it gets a test that states it rather than a comment.
- [x] Nothing in this module reads or writes a `Project`. It takes the numbers
      it needs, so M4 can call it without a model and M3 can call it per
      mouse-move without allocating one.

> **Amended before building.** The bound was "half a tick", which is out by one
> rounding: converting a sample to ticks rounds once and converting back rounds
> again, and the two compose. At 137.3 BPM the worst case is 11 samples against
> a half-tick of 10.92, so the literal line fails for a reason that is
> arithmetic rather than a bug. The exact-on-the-grid half is unchanged and is
> the claim everything actually leans on — measured exact at six tempos, two
> denominators, out to an hour of audio. Reasoning in
> [the plan](plans/phase_3_time_and_snapping.md).

## Implements

F-16, F-17, F-18, F-19. D-11, D-26, D-52. The *Time* section of
[03-data-model.md](../03-data-model.md), which owns the rule that samples are
the truth and everything else is a view.

## Notes

**Done. Every acceptance line passes**, one of them after being amended before
any code was written — see the note above *Implements*.

**960 ticks a beat, and the number is load-bearing.** Every division from 1/1
to 1/32, straight and triplet, lands on a whole number of ticks at 4/4, 3/4,
6/8 and 7/8. 1000 would not: a triplet is two-thirds of its straight division
and 1000 is not divisible by 3, so every triplet would have become a rounding
error accumulating down the timeline.

**Grid positions round-trip exactly**, at six tempos × four time signatures,
across four hundred bars — which is the claim the rest of the application
leans on, because it is what makes a quantised arrangement stay quantised.
Arbitrary sample positions cost half a tick plus half a sample, the amendment
above.

**`Division` moved from `model.py` to `time.py`.** A grid division is a fact
about time, not about a project, and leaving it in the model would have made
this module — which is otherwise a leaf that imports nothing from `core` —
depend on the data spine for one enum. `model` now imports it the other way,
along with `SAMPLE_RATE`. Small, and worth doing while there is one caller
rather than six.

### The mutations were named in the plan before the tests existed

That was a deliberate response to [phase 2](phase_2_curve_evaluation.md),
where the two mechanisms the plan argued hardest for both shipped with tests
that could not detect their absence. Writing the list first meant each test had
a specific failure to be aimed at. All nine are caught:

| mutation | tests that failed |
|---|---|
| nearest → always the lower grid line | 21 |
| drop the triplet factor | 25 |
| ticks 960 → 1000 | 24 |
| only the lower grid neighbour (idempotence) | 21 |
| `snap_override` ignored | 2 |
| forget the edge to the right | 1 |
| ignore clip edges entirely | 1 |
| grid first, edges as an afterthought | 1 |
| BPM counts the denominator note | 1 |

⚠️ **Four of those are held up by a single test each**, which is thin. They are
the ones whose behaviour is a *choice* rather than an arithmetic property —
what BPM counts, whether edges compete with the grid on equal terms — so there
is exactly one assertion that can distinguish right from wrong, and deleting it
would silently remove the coverage. Recorded so a later reader knows those
tests are load-bearing rather than decorative.

### Inherited by M3

| | |
|---|---|
| `to_bar_beat` / `from_bar_beat` | `BarBeat(bar, beat, tick)`, 1-based bar and beat, `str()` gives `1.1.000` |
| `snap(...)` | keyword-only, `division=None` means off — which is what a disabled setting *and* a held `Alt` both resolve to |
| `edges` | must be sorted; the search is a bisect plus two grid candidates, so cost does not grow with clip count |
| `effective_snap(project, channel)` | F-18, in `model.py` because it takes model types |

Nothing in this module reads a `Project`, so M4 can call it with no model in
reach and M3 can call it per mouse-move without building one.
