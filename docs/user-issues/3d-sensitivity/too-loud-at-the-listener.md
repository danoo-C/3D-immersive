# Why a placed channel at (0, 0, 0) distorts, and a bypassed one does not

**Status:** explained; nothing changed · **Written:** 2026-09-27 ·
**Measured at:** `46b71cb` on `m3-timeline`, through SADIE II D1, on
`FEA2_DRUMS_2.wav` from `test-samples/`, its loudest 40 s (116–156 s)

**Reported:** A drum channel from a mastered song, placed at (0, 0, 0),
clips and is badly distorted. With HRTF bypass on, the same channel sounds
exactly as mastered, right at the edge of clipping but clean.

## The short answer

A placed channel passes through two gains that a bypassed one never meets:

- **Distance, +14 dB.** (0, 0, 0) is nearer than the minimum distance of
  0.2 m, so it plays as a source 0.2 m away, which is five times the
  amplitude of the same source at 1 m.
- **The HRTF set's own level, about −5 dB.** SADIE II D1, as the engine
  loads it, plays about 5 dB below its input for a source straight ahead.

Together that is about +9 dB over the stem. A stem mastered to peak at
−0.3 dBFS then peaks near +8 dBFS. With the limiter on, it takes up to 8 dB
off the drums, and 1 dB or more for half of the time they sound. On drums,
that is the distortion you hear. With the limiter off, 5 % of the samples go
past full scale and clip outright.

Bypass skips the HRTF and the distance gain (05, *HRTF bypass*), so the
stem comes out bit for bit as it went in, at the edge of full scale and no
further.

The previous report, [why a centimetre swings a sound](README.md), is the
same position seen from the other side. (0, 0, 0) is where a new channel
starts, and it is both the most sensitive place and the loudest.

## Measured

The drum stem, its loudest 40 s, rendered at 512 frames:

| | Peak | Samples past full scale, limiter off | Limiter on: most taken off | …1 dB or more, of the time it sounds |
|---|---|---|---|---|
| The stem as it is | −0.34 dBFS | 0 | — | — |
| Bypassed | −0.34 dBFS | 0 | 0.2 dB | 0 % |
| Placed 2 m ahead | −12.2 dBFS | 0 | 0 | 0 % |
| Placed 1 m ahead | −6.2 dBFS | 0 | 0 | 0 % |
| **Placed at (0, 0, 0)** | **+7.8 dBFS** | **5.1 %** | **8.1 dB** | **50 %** |

The 0.2 dB taken off the bypassed stem is the limiter's soft knee, which
starts turning a signal down 1 dB under the ceiling (D-123). The stem's
peaks reach into it.

## Where each gain comes from

**Distance** (D-21, 03 *Coordinate system*). Level is
`(1 m / r) ^ rolloff`. With rolloff 1 that is 6 dB more for every halving of
the distance. It stops rising at `min_distance`, 0.2 m, so that a source on
top of your head is not infinitely loud, but it stops at +14 dB:

| Distance | Level against 1 m |
|---|---|
| 0.2 m or nearer, (0, 0, 0) included | +14 dB |
| 0.5 m | +6 dB |
| 1 m | 0 dB |
| 2 m | −6 dB |

**The HRTF set's level.** The set is scaled when it is loaded so that its
mean energy per ear, over all its directions, is 0.25. That is S0's target,
chosen for headroom (M4 phase 1), and it is −6 dB on average. It was never
set to match bypass. Measured with white noise one metre straight ahead, a
little above that average, it comes out 5.3 dB lower on the left and 4.2 dB
lower on the right than it went in. The 1.1 dB between the ears is SADIE's
own, as the first report found.

**The mono point** (D-16). A placed stereo channel is heard as one point,
its two sides averaged. For this stem that costs 0.5 dB, since drums are
mostly in the middle. A wide stereo stem, whose sides share little, loses
up to 3 dB.

At (0, 0, 0) the sum is about +14 − 5 − 0.5, roughly +8.5 dB. The measured
peak rose by 8.2 dB, from −0.34 to +7.8 dBFS.

## Why the limiter distorts here

The master limiter is a safety catch (D-54). It is built to shave off the
odd peak a mix did not expect, not to hold a drum stem 8 dB down. It sees
1.5 ms ahead and lets go over 50 ms. At 8 dB, it turns down every hit and
lets go between them. A kick's low end has cycles 10 to 20 ms long, so the
gain changes within the waveform itself, and that reshaping is heard as
distortion. Any limiter asked to take 8 dB off drums sounds like this. It is
the request, not the limiter.

The channel's meter showed it. It reads after the distance gain (D-117), so
placed at (0, 0, 0) it showed the channel far hotter than the stem, while the
bypassed channel's meter sat at the edge, where the stem was mastered.

## Also: placed 1 m ahead is about 6 dB quieter than bypassed

The other way round, a placed channel one metre ahead plays about 6 dB below
the same channel bypassed: the set's −5 dB and the mono point's −0.5 dB.
Switching bypass on a channel 1 m ahead therefore jumps it by about 6 dB.
That is not what this report is about, but it is the same cause from the
other side. The spatial path's level was never set to match bypass.

## What you can do today

Move the channel away before listening to it placed. At Y = 1, one metre in
front, this stem peaks at −6 dBFS and the limiter does nothing. At Y = 2 it
peaks at −12 dBFS. Set its level with the channel's gain, and keep an eye on
the channel's meter.

## What could change (none of it is done)

A fuller design grew out of this list: [level as mixed](level-as-mixed.md).

1. **Start new channels one metre in front**, at (0, 1, 0), the reference
   distance, instead of at the listener. There the distance gain is exactly
   0 dB and nothing flips from ear to ear. It is a one-line change, and
   channels already placed stay where they are.
2. **No boost nearer than the reference distance.** A source closer than 1 m
   would play as it does at 1 m, so placing a stem could never push it past
   its own level. The clamped distance models game audio uses, OpenAL's
   among them, work this way. What it gives up is a source growing louder as
   it comes right up to you, which is realistic and occasionally wanted. It
   would amend D-21. It could be a default, with `min_distance` raised to
   1 m, or the law itself.
3. **Match the placed level to bypass at one metre ahead**: scale the set by
   about +5 dB when it is loaded, instead of to S0's 0.25, so that placing a
   channel in front of you does not change how loud it is. On its own this would make (0, 0, 0)
   louder still, so it only makes sense together with 2. It should also be
   checked by ear, since loudness through an HRTF is not one number across
   frequencies.
4. **Not a different limiter.** Its design is fixed on purpose (D-54), and
   taking 8 dB off drums distorts in any limiter. The answer is not asking it
   to.

The recommendation is 1 and 2 together: a new channel then plays at the
stem's own level, and no position can push it past that level. Then 3,
after a listening check.

## How this was measured

`FEA2_DRUMS_2.wav` decoded and resampled to 48 kHz as an import does, and
its loudest 40 s by RMS, from 116 s, played on one channel through the
engine at 512 frames with SADIE II D1. Each position was rendered once with
the limiter off and once with it on, read through the engine's latency. The
reduction is the ratio of the two, sample by sample, wherever the stem is
not silent. The set's own level is white noise at −26 dBFS, one metre
straight ahead, RMS out against RMS in.
