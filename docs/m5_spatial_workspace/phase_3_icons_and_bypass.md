# M5 · Phase 3 — What an icon says, and the bypass strip

**Status:** ✅ · **Plan:** [plans/phase_3_icons_and_bypass.md](plans/phase_3_icons_and_bypass.md)

## Goal

An icon tells its channel's state at a glance. Its radius shows distance,
larger when nearer, and its opacity shows gain. A muted channel's icon
drops to 25% opacity and a soloed one glows. Bypassed channels, which have
no position, appear as chips in a strip along the bottom of the top view.
A click on a chip selects the channel, and a click on its ⊘ un-bypasses
it, which puts it back on the canvases where its position was. The strip
hides when nothing is bypassed.

## Scope

**In:** radius by distance, opacity by gain, mute and solo, in both ortho
views; the bypass strip, its chips, selecting and un-bypassing from it.

**Out:** the same in the 3D view → phase 4, which draws icons the same way.

## Acceptance

- [x] An icon nearer the head is larger than one farther away, by a rule
      the plan sets, and a quieter channel's icon is fainter. *D-146: 10 px
      at 1 m, 2 px less each doubling; opacity like loudness, above a 40%
      floor.*
- [x] A muted channel's icon is at 25% opacity, and a soloed one's has a
      glow. *And a channel silenced by another's solo is at 25% too.*
- [x] A bypassed channel is a chip in the strip with its name and ⊘, and
      is on no canvas. The strip is hidden when no channel is bypassed.
- [x] A click on a chip selects its channel. A click on ⊘ un-bypasses it,
      as one edit, and its icon reappears at its kept position.
      *`test_bypass_strip.py`; looked at, see the Notes.*

## Implements

*Bypassed channels* and *Icons and depth* in
[04-ui-spec.md](../04-ui-spec.md); D-36.

## Notes

Appended while building.

**Built (2026-09-30)** in four steps: the rules in `look.py`, the icons
drawn by them, the strip, and the strip in the window.

**A channel silenced by a solo is drawn as a muted one.** 04 named mute
and solo, and not the channels a solo silences. They are as unheard as a
muted one, and `audible()` already decides both for the engine and the
headers. So they are at 25% too, and the glow on the soloed says why.

**The strip is under the top view, not over it** (D-147). It takes its
room from the top view while it shows, so the head moves up by half its
height. A drag under way when a channel is bypassed from elsewhere is
dropped by phase 2's rule, so nothing moves under the pointer.

**Looked at.** Both views with six channels: a near source, a soloed one,
a muted one, one at −12 dB, a far linked pair, and a pair at −30 dB. The
near is plainly larger, the far pair small with its L and R still
legible, the −30 dB pair faint but not muted-faint, and the soloed one's
glow draws the eye. With a solo on, everything else fades to a quarter,
which reads as "only this is heard". And the whole workspace with six
bypassed channels: two rows of chips, the long names cut short, the
selected chip outlined, and the ⊘ under the pointer lit.
