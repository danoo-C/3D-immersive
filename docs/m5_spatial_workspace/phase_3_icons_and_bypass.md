# M5 · Phase 3 — What an icon says, and the bypass strip

**Status:** in progress · **Plan:** [plans/phase_3_icons_and_bypass.md](plans/phase_3_icons_and_bypass.md)

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

- [ ] An icon nearer the head is larger than one farther away, by a rule
      the plan sets, and a quieter channel's icon is fainter.
- [ ] A muted channel's icon is at 25% opacity, and a soloed one's has a
      glow.
- [ ] A bypassed channel is a chip in the strip with its name and ⊘, and
      is on no canvas. The strip is hidden when no channel is bypassed.
- [ ] A click on a chip selects its channel. A click on ⊘ un-bypasses it,
      as one edit, and its icon reappears at its kept position.

## Implements

*Bypassed channels* and *Icons and depth* in
[04-ui-spec.md](../04-ui-spec.md); D-36.

## Notes

Appended while building.
