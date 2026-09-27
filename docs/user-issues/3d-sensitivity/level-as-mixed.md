# Level as mixed: placing a stem without changing how loud it is

**Status:** proposed, not built · **Written:** 2026-09-27 · **Measured at:**
`15720c6` on `m3-timeline`, through SADIE II D1, on the 23 stems in
`test-samples/`

**Asked for:** an "intelligent normalizer", switched on for a project, that
keeps each file at its original level until it is far enough away that it
should start getting quieter. It follows from the two reports beside it:
[a centimetre swings a sound from ear to ear](README.md), and
[a channel at (0, 0, 0) distorts](too-loud-at-the-listener.md).

## The idea

With it on, **a placed channel is as loud as the same channel bypassed,
wherever it is, until it is farther away than a distance you choose**, one
metre by default. Past that distance, and only then, it gets quieter with
distance as it does now.

Where it is still decides everything you hear about direction. It just stops
deciding how loud the channel is.

## What changes a placed stem's level today

Four things, all measured. None of them is a fact about the music: each is
a property of the engine or of the file, known before a note plays.

| What | By how much | Measured on |
|---|---|---|
| **Distance** nearer than 1 m | up to **+14 dB** (0.2 m and nearer) | the law, D-21 |
| **The HRTF set's level** | **−5.0 dB** straight ahead | SADIE II D1, K-weighted pink noise |
| **Direction** | **−3.8 dB** (below) to **+1.7 dB** (60° right) against the front, median −1.2 | all 8802 of SADIE's directions |
| **Folding a stereo stem to one point** | **0 to −5.3 dB** | 21 of the 23 stems, 60 s each |

The fold, stem by stem: the three bass stems and `Insert 13` lose nothing,
and `DRUMS_2` and the vocal lose 0.4 dB and 0.2 dB. The violins and leads
lose 1 to 2 dB, `piano` 2.1 dB, and the two `rythm1` stems 3.0 dB each.
`Insert 9` loses 5.3 dB, which means part of it is out of phase between its
sides and cancels when they are added. (`kick isloation` and `Insert 34` are
silent in the minute measured.)

So the drum channel at (0, 0, 0) was +14 − 5.0 − 0.4, about +8.6 dB over
itself. A violin placed one metre behind you would be −5.0 − 2.4 − 1.6, about
−9 dB under itself. Neither number is one anybody chose.

## What "genuinely good" should mean

1. **Loudness, not peaks.** The HRTF changes a stem's spectrum, so matching
   peaks would leave placed stems sounding quieter or louder than bypassed
   ones. Everything is matched on the loudness a listener hears, with the
   broadcast standard's weighting (ITU-R BS.1770's K-weighting), over both
   ears together.
2. **Never touch the cues.** How you hear where a sound is comes from the
   difference between the ears, the delay between them, and the spectrum's
   shape. The normalizer only scales a channel's overall level. The
   difference between the ears stays exactly what the measured head gives.
3. **Fixed, not adaptive.** Every correction is worked out once, when the
   HRTF set is prepared or when a sample is imported. None of them follows
   the signal as it plays. A normalizer that listened and adjusted would be a
   compressor by another name. It would change the mix's dynamics, which is
   the one thing a mastered stem must keep, and what you heard would depend
   on where playback started.
4. **Free while playing.** The corrections fold into the bank's filters and
   the clips' gains. A block does the same work it does now.
5. **Distance still means something.** Past the full-level distance, rolloff
   makes a source quieter exactly as it does today.

## The pieces

Three of these are corrections the engine should make anyway, and two are
what the switch turns on.

**Always, switch or not:**

1. **Calibrate the set to bypass.** When the set is prepared, scale it so a
   source straight ahead is as loud as the same sound played straight to
   both ears: +5.0 dB for SADIE II D1. This replaces phase 1's fixed 0.25,
   which was chosen for headroom and never matched to anything. It also
   closes the 6 dB jump when switching bypass on a channel one metre ahead.
2. **Fold a stereo stem without losing it.** When a stereo file is imported,
   measure how much its mono point loses, and give it that back as a gain on
   a placed channel's copy of the clip. It is capped at +6 dB, since a stem
   that loses more than that is mostly out of phase. A bypassed channel
   keeps its sides and needs none. A stem that loses more than 3 dB, like
   `Insert 9`, sounds different folded, not only quieter, and the pane could
   say so.
3. **A centre, not a flip.** Inside the minimum distance, 0.2 m, fade the
   source from placed to the stem itself as it nears the centre: the filter
   towards flat, the delay between the ears towards none. At (0, 0, 0) it is
   then heard as it is, in your head, as bypass hears it. Moving outward, it
   becomes a placed source by 20 cm, and passing through the listener is a
   pass through the middle rather than a jump from one ear to the other.
   The bank keeps each response's delay apart from its shape (M4 phase 2),
   so the two fade without comb filtering.

**With "Level as mixed" on:**

4. **No boost nearer than the full-level distance.** Nearer than it, the
   gain is 1. Past it, `(distance / r) ^ rolloff`. It is D-21's law with the
   minimum distance raised to the reference, and what OpenAL calls its
   clamped models. The distance is `ref_distance`, 1 m by default, and could
   be a field.
5. **The same loudness in every direction.** Each measured direction's pair
   is scaled so its loudness equals the front's, which is 5.5 dB of range
   evened out for SADIE, folded into the filters. The difference between the
   ears, the delay and the spectrum stay as measured. What is lost is that a
   source behind you, or below you, is also a little quieter, which a real
   room does. That is why it is behind the switch and not always on.

Off, a project gets today's physical behaviour on top of the three fixes:
closer is louder, and some directions are quieter than others.

## What it would sound like

On the drum stem, with the switch on:

| Where | Today | With it |
|---|---|---|
| (0, 0, 0) | +7.8 dBFS peaks, up to 8 dB of limiting | its mono point, in your head, at the stem's loudness: peaks near its own −0.34 dBFS (estimated) |
| 1 m ahead | −6.2 dBFS peaks | the stem's loudness, peaks near −1 dBFS (estimated) |
| 2 m ahead | −12.2 dBFS | 6 dB under the stem, from distance alone |

The one thing it cannot do is keep a full-scale stem off the limiter at the
side. There the nearer ear is up to 2.7 dB louder than it is with the
source in front, after the directions are evened out. That difference is
the cue that says "beside you", and removing it would remove the placing.
A stem mastered to the edge of full scale and placed to the side will
therefore touch the limiter by up to about 3 dB. Channel gain or master gain
3 dB down avoids it.

The whole mix is a separate matter. Twenty-three stems, each at its mix
level, sum past full scale just as the unmastered mix did. The master gain
is where that is set.

## What it costs

- **Preparing the set:** the loudness of every direction, from the bank's
  filters. Under a second for SADIE, and cached with the bank.
- **Importing:** one K-weighted pass over a stereo file, on the worker that
  already builds its peaks.
- **Playing:** nothing for pieces 1, 2, 4 and 5, which are gains folded in.
  For piece 3, one blend per ear, only for a channel inside 0.2 m.
- **The project file:** one switch, probably `distance.keep_level`, true for
  new projects.

## What it would need decided

- Loudness by BS.1770 K-weighting, fixed rather than adaptive, and the set
  calibrated to bypass in place of phase 1's 0.25.
- The fold correction and its cap, and whether the pane warns about wide
  stems.
- The centre fade, which replaces "(0, 0, 0) is straight ahead".
- The switch: its name, its home in the project, and that it is on for new
  projects. D-21 and D-16 amended to match.

## Where it would go

As an M4 phase of its own, before the benchmark: the benchmark should
measure the graph as it will ship, and the listening phase should hear it.
M4's acceptance is positions "audibly, correctly placed". A +14 dB surprise
at the default position, or a −9 dB one behind you, is not correct placing
for stems that were mixed before they were placed.
