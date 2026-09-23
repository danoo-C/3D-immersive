# Plan — M1 · Phase 3 — Time and snapping

**Written:** 2026-09-21 · **Status:** ✅ complete

## Approach

`core/time.py`, taking numbers and returning numbers. Nothing in it reads a
`Project`: M4 calls it with no model in reach, and M3 calls it on every
mouse-move and should not be building one to ask what time it is.

Samples stay the truth (D-11); seconds and bars:beats are views computed on
demand and stored nowhere.

### Ticks, and why 960

Bars:beats needs a sub-beat unit to be a *position* rather than a range, and
`04`'s transport readout is already drawn as `1.1.000` — three fields, the
third zero-padded to three digits.

**960 ticks per beat.** The number matters because F-16 requires triplets, and
a resolution that cannot express a triplet exactly turns every one into a
rounding error that accumulates down the timeline. Checked across every
division from 1/1 to 1/32, straight and triplet, at both 4/4 and 6/8: at 960
**every one lands on a whole number of ticks**. 1000 would not — a 1/16 triplet
is 2/3 of 1/16, and 1000 is not divisible by 3.

A "beat" here is the time signature's denominator note, and **BPM counts
quarters** regardless of it, which is what every DAW means by the number. So at
6/8, 120 BPM gives a beat of 12 000 samples rather than 24 000, and a bar is
three quarters long. Written down because it is a convention rather than a
derivation, and the alternative reading is defensible enough that someone will
eventually assume it.

### ⚠️ The round-trip bound is half a tick *plus half a sample*

The phase doc's acceptance says the round-trip error "never exceeds half a
tick". That is out by one rounding. Converting a sample to ticks rounds once
(≤ half a tick), and converting back to samples rounds again (≤ half a sample),
and the two compose. Measured:

| BPM | half a tick | the real bound | worst seen |
|---|---|---|---|
| 120 | 12.50 | 13.00 | 12 |
| 137.3 | 10.92 | 11.42 | **11** |
| 89.71 | 16.72 | 17.22 | **17** |
| 40 | 37.50 | 38.00 | 37 |

At 137.3 BPM the worst case is 11 samples against a half-tick of 10.92 — a
literal reading of the line fails, for a reason that is arithmetic rather than
a bug. The acceptance is amended to *half a tick plus half a sample*.

**Grid positions are a different and stronger claim, and it holds exactly.** A
position built from bars:beats round-trips back to the identical sample at
every tempo and denominator tried, out to an hour of audio, with no error at
all. That is the property everything downstream actually leans on — an
arrangement quantised to the grid stays quantised.

### Floats, not fractions

Exact rational arithmetic would make the above trivially true and is the
obvious defensive choice. It is not needed: at one hour (172.8 M samples)
float64's relative precision leaves an absolute error around 4e-8 samples,
eleven orders of magnitude below the rounding that is already happening.
Verified rather than assumed — the grid round-trip above was measured with
floats, over four million ticks. M3 calls this per mouse-move and `Fraction`
is roughly two orders of magnitude slower.

### Snapping

One function over explicit candidates: the two grid lines bracketing the
position, plus any clip edges supplied. **Nearest wins outright** — F-17 asks
for the grid *and* clip edges, and a reading where the grid wins ties or is
tried first would make a clip edge sitting just inside a grid line
unreachable, which is the case people snap to most.

Clip edges arrive as a sorted sequence so the caller can `bisect` rather than
scan; M3 keeps one such list per channel and rebuilds it on edit.

## Steps

1. **Samples, seconds, ticks.** `samples_per_beat`, and conversion both ways
   between samples and a `(bar, beat, tick)` position.
   *Test:* grid positions round-trip **exactly** at 120, 124, 137.3, 89.71, 200
   and 40 BPM, at 4/4 and 6/8, across four million ticks. Arbitrary sample
   positions round-trip within half a tick plus half a sample. Seconds are
   `samples / rate` and nothing more.

2. **The grid.** The sample spacing of a division, straight and triplet.
   *Test:* every division from 1/1 to 1/32 and every triplet lands on a whole
   number of ticks at 4/4 and 6/8 — the property that made 960 the right
   number. Spacings are in the expected ratios: a 1/8 is half a 1/4, a triplet
   is two-thirds of its straight division.

3. **Snapping to the grid.** Nearest line, with the "off" case returning the
   position untouched.
   *Test:* idempotent — snapping an already-snapped position returns it
   unchanged, because a snap that drifts on repeated application moves clips
   nobody dragged. Ties resolve consistently rather than by float accident.

4. **Snapping to clip edges, and the override.** Edges merged into the
   candidate set; `Channel.snap_override` beating `Project.snap`, including
   when it disables snapping; `None` inheriting.
   *Test:* a clip edge placed deliberately just *inside* a grid line wins, which
   is the assertion that separates "nearest of both" from "grid, then edges".

5. **D-52, asserted rather than commented.** Build an arrangement, change the
   BPM, and check every clip `start` and every keyframe `t` is unchanged while
   their bars:beats readings are not.
   *Test:* exactly that. It is the most surprising rule in the model and the
   one most likely to be "fixed" by someone who thinks it is a bug.

Five steps, inside the six [09-workflow.md](../../09-workflow.md) allows.

## Files

```
src/immersive/core/time.py        new
tests/test_time.py                new
phase_3_time_and_snapping.md      amended — the round-trip bound
docs/03-data-model.md             amended — ticks, and what BPM counts
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A test asserts a mechanism without distinguishing it — the phase 2 failure | Two mechanisms shipped untested while the suite looked green | Mutations run against the finished suite, at minimum: nearest→floor, drop the triplet factor, grid-before-edges, `snap_override` ignored, ticks 960→1000 |
| Tie-breaking at exactly half a division | Snapping flickers between two lines under a mouse that is not moving | Resolve ties by a stated rule (toward the later candidate) and test it, rather than letting float comparison decide |
| The 6/8 convention is wrong | Every bars:beats reading in the application is wrong at compound time signatures, and looks right at 4/4 | Stated explicitly above, tested at 6/8 as well as 4/4, and written into `03` so it is a decision rather than an implementation detail |
| Snapping cost at a few hundred clips | M3 drags feel sticky | Edges arrive sorted; the search is a bisect over them plus two grid candidates, independent of clip count |
| `bpm` of zero or negative | Division by zero deep inside a conversion | [Phase 1](../phase_1_dataclasses.md)'s validator already rejects it; this module raises rather than returning an infinity, and says which argument |

The genuine unknown is **whether `(bar, beat, tick)` is the right return
shape**. It is what the ruler and the transport readout need, and it is
three fields where M4 wants none. Nothing in the engine converts to bars at
all — BPM never affects playback (D-52) — so the cost falls entirely on the UI,
which is the right place for it. Recorded because a reader may expect the
conversion to be hot, and it is not: the engine never calls it.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The ruler, and its bars:beats ↔ min:sec toggle (F-19) | M3 — this phase computes what it displays |
| Holding `Alt` to bypass snap | M3; it is an input gesture resolving to the "off" this phase provides |
| Drawing the grid | M3 |
| A tempo map | Never (D-26) |
| Deciding what a drag *does* once snapped | [Phase 4](../phase_4_undo_stack.md)'s commands |

## Outcome

**Every acceptance line passes**, and this is the first phase where the plan
did not have to amend one *after* writing code — the round-trip bound was
caught while planning, which is where the amendment cost nothing.

**Naming the mutations in advance worked.** Phase 2 ended with two mechanisms
shipped behind tests that could not detect their absence, so this plan listed
the mutations before any test existed. All nine are caught on the first pass.
The table is in [the phase Notes](../phase_3_time_and_snapping.md).

The mechanism is not that the mutations *are* the tests — it is that having a
concrete failure in mind while writing an assertion makes the difference
between a test that mentions a behaviour and one that distinguishes it. Cheap,
and it took about five minutes to write the list.

⚠️ **Four behaviours are held up by one test each.** They are the ones that are
a *choice* rather than an arithmetic property: what BPM counts, whether clip
edges compete with the grid on equal terms. There is exactly one assertion that
can tell right from wrong in each case, so deleting it removes the coverage
silently. Recorded rather than papered over, and noted in the phase doc so the
next reader knows those are load-bearing.

**What the plan got wrong.** Nothing measurable, but it under-specified one
thing: it did not say where `Division` should live. It ended up moving from
`model.py` to `time.py`, because a grid division is a fact about time and
leaving it in the model would have made this module — otherwise a leaf that
imports nothing from `core` — depend on the data spine for one enum. Worth
doing at one caller rather than six, but it was a decision the plan should have
made rather than discovered.

**Inherited by M3:** the conversions, `snap`, and `effective_snap`. Details in
the phase Notes.
