# 03 — Data Model

## Coordinate system

Right-handed, metres, **listener fixed at the origin facing +Y**.

| Axis | Positive direction |
|---|---|
| X | listener's **right** |
| Y | **front** |
| Z | **up** |

Which maps onto the two editable views like this:

```
  TOP view (X / Y)              FRONT view (X / Z)
  screen right = +X             screen right = +X
  screen up    = +Y (front)     screen up    = +Z (up)
```

### Converting to HRTF lookup

SOFA's spherical convention differs: azimuth 0° is front and increases
**counter-clockwise** (so 90° is the listener's left), elevation is measured up
from the horizontal plane. Its cartesian frame is +x front, +y left, +z up.

```
r   = sqrt(x² + y² + z²)
az  = degrees(atan2(-x, y)) % 360     # -x because +az goes left
el  = degrees(asin(z / r))            # 0 at ear level, +90 overhead
```

`r` is clamped to `distance.min_distance` (default 0.2 m) before attenuation, so
a source dragged onto the head does not blow up. Attenuation is then
`(ref_distance / r) ** rolloff` — `rolloff` 1.0 is the physically correct
inverse-distance law, and lower values soften it (D-21).

## Time

The single source of truth for time is **samples, int64, at the project rate**.
Everything else is a view:

- Seconds — `samples / sample_rate`, for the min:sec ruler and display.
- Bars:beats — derived from `bpm` and `time_signature`, for the grid and snap.

BPM never affects playback. It exists only to draw a grid and quantise edits.

### ⚠️ Changing the BPM moves the grid, not the material

Because positions are stored in samples, changing the tempo re-draws the grid
underneath an arrangement that does not move (D-52). Material lined up to bars
at 120 BPM is **not** lined up at 124: the clips are where they always were,
and the bar lines have slid out from under them.

This is the direct consequence of the sentence above, and it is written here
rather than left to be inferred because the opposite is what most people
expect. The alternative — rescaling every clip start and keyframe time with
the tempo — would make BPM a destructive edit that changes where everything is
while changing nothing about how anything sounds, and it rounds badly whenever
a clip's length is not a whole number of ticks.

Set the tempo before arranging. The grid is a ruler, not a transform.

### Length

A project's length is **derived, not stored** (D-53): it is the end of the last
clip on any channel, and zero for a project with no clips. Nothing has to be
maintained when a clip moves, and there is no stored end marker that can
disagree with the material.

Automation extending past the last clip is retained but does not extend the
length — a curve with nothing to move is not content. Where a render needs to
run past the last clip, that is the render range's job (F-53), not a property
of the project.

## Entities

```
Project
├── sample_rate      48000, fixed
├── bpm              float
├── time_signature   [num, den]
├── snap             SnapSetting            global default
├── hrtf             HrtfRef
├── distance         { rolloff, min_distance, ref_distance }
├── master           { gain_db, limiter_on }
├── media_pool       [MediaFile]
└── channels         [Channel]              ordered, top to bottom

MediaFile
├── id               "m-" + 8 hex digits
├── path             relative to the project file
├── name
├── source_rate      as found on disk
├── channels         1 or 2 (stereo is downmixed at play time)
├── frames           length at project rate, after resampling
└── hash             for relink and cache invalidation

Channel
├── id               "c-" + 8 hex digits
├── name
├── color            hex, from the channel palette
├── gain_db
├── mute
├── solo
├── hrtf_bypass      bool   true → straight to the stereo bus, unprocessed
├── pan              float  -1 left … 0 centre … +1 right; bypass only
├── snap_override    null → inherit Project.snap
├── position         { x, y, z }            used where no automation exists
├── automation       { "pos.x": Curve, "pos.y": Curve, "pos.z": Curve,
│                      "gain": Curve, "pan": Curve }   any key may be absent
└── clips            [Clip]                 sorted by start, never overlapping

Clip
├── id               "k-" + 8 hex digits
├── media_id         → MediaFile
├── start            samples on the timeline
├── offset           samples into the source: the crop point
├── length           samples
├── gain_db
├── fade_in          { length, shape }      shape: linear | equal_power
└── fade_out         { length, shape }

Curve
└── keyframes        [Keyframe], sorted by t, unique t

Keyframe
├── t                samples, absolute timeline time
├── value            float
├── interp           linear | ease | hold      governs the segment *after* it
└── handles          { out: [dt, dv], in: [dt, dv] }   only when interp == ease
```

### Ids

`<kind>-<8 hex digits>`, where the kind is `m` for media, `c` for a channel and
`k` for a clip. Unique across the whole project, not merely within their own
kind, so one lookup table answers "what is this id" without needing to know
what it refers to first.

Short rather than a uuid because a `.3dim` is meant to be diffable and
hand-editable (D-13, F-2), and 36 characters in every clip works against both.
Eight hex digits are safe because ids are minted by checking against what the
project already holds and regenerating on a clash — a bare 32-bit space has
roughly a 1% birthday collision at ten thousand clips, which is too close to
rely on, while generate-check-regenerate has no such bound.

Uniqueness is *checked* as well as minted carefully. A hand-editable format
means a person can introduce a duplicate that no minting strategy would have
prevented.

**Keyframes have no id.** They are identified by `t` within their curve, which
is why `t` must be unique — two keyframes at the same time are the same
keyframe twice. The consequence belongs to M6: dragging a keyframe onto
another's time is a collision to resolve, not a reordering.

> Earlier versions of this document said `MediaFile.id` was a uuid while the
> example below used `m-3f2a`, `c-01` and `k-01` — which were not a scheme at
> all but mnemonics written by hand (the clip on *Kick* was `k-01`, the one on
> *Backing mix* `b-01`). The example now uses real ids.

### Rules

- A channel's position in `Project.channels` **is** its order, top to bottom.
  There is no stored `index` (D-61) — two homes for one fact is the thing
  [doc-system.md](doc-system.md) §2 exists to prevent, and a file whose list
  order and index fields disagreed had no defined meaning.
- Clips on one channel never overlap. Dropping onto an occupied span trims the
  existing clip (magnetic behaviour); a modifier opts out and rejects the drop.
- `offset + length` must not exceed `MediaFile.frames`.
- A channel with no keyframes for an axis uses its static `position` component.
  With one keyframe, that value holds for the whole timeline.
- Before the first keyframe and after the last, the curve holds flat.
- Automation is stored per channel at **absolute** timeline time (D-7).
- `hrtf_bypass` is a plain boolean with no curve. It is deliberately not
  automatable (D-34).
- When `hrtf_bypass` is true, `position` and the `pos.*` curves are **inactive
  but preserved**. Nothing is deleted, and turning bypass off restores the
  previous spatial behaviour exactly (F-42). The same holds in reverse for
  `pan` — it survives while the channel is spatialised.
- A clip edge that does not coincide with the media file's own start
  (`offset == 0`) or end (`offset + length == MediaFile.frames`) receives an
  **implicit 32-sample linear fade** at playback time (D-42). It is not stored
  here, not shown in the UI, and an explicit fade replaces rather than adds to
  it. A full-length clip placed at 0 is therefore bit-transparent, which is
  what the bypassed-stem case needs.
- `pan` is meaningful only under bypass. On a mono source it is a
  constant-power pan; on a stereo source it is a balance, attenuating the
  opposite side rather than folding the image.
- **Solo is additive** (D-62): several channels can be soloed at once, and
  while any of them is, every non-soloed channel is silent. A channel that is
  both soloed and muted stays muted — mute is the more deliberate gesture, and
  somebody who muted a channel and then soloed it was auditioning the rest.
  Bypassed channels obey solo like any other; bypass is about spatialisation,
  not about the mix bus (D-33).

### Evaluating a curve

`Curve.value_at(t)` finds the bracketing pair and interpolates:

- `hold` — the left keyframe's value until the right one.
- `linear` — straight line.
- `ease` — cubic bezier defined by the two keyframes and their facing handles,
  solved for `t` then evaluated for value. Handle `dt` is clamped so the curve
  can never double back in time.

The engine calls this once per channel per parameter per block.

### ⚠️ Linear interpolation passes through the head

The `pos.*` curves interpolate X, Y and Z independently, in cartesian space. A
move between two points on opposite sides of the listener therefore travels in
a straight line **through the origin**, not around it.

The 0.2 m clamp (see *Coordinate system*) stops the distance gain from blowing
up, but the perceived direction still flips abruptly as the source crosses from
one side to the other. This is expected behaviour, not a bug — it is a direct
consequence of having no motion-path presets in v1 (D-25).

The fix, when path presets arrive, is **orbit interpolation**: interpolating
azimuth and radius rather than cartesian coordinates, so a source moving from
left to right arcs around the listener at constant distance. That is the first
candidate on the list; see the "later, maybe" section of
[00-overview.md](00-overview.md).

## Project file

`.3dim` — UTF-8 JSON, pretty-printed with sorted keys so it diffs cleanly in
git. A `schema_version` integer drives forward migration on load. Fields added
later default on read — a project written before `hrtf_bypass` existed loads
with it `false`, which is the previous behaviour.

Beside it, `app_version` records the build that wrote the file (D-60). It is
not `schema_version` and does not drive anything: two builds can both write
schema 1 and disagree about a default, and when a project loads wrong the
writing version is the first thing anyone asks for. There are deliberately
**no timestamps** — a `modified` field would change on every save and produce
a diff even when nothing about the music did, which costs exactly the
git-friendliness D-13 was for. The filesystem already knows.

```json
{
  "schema_version": 1,
  "app_version": "0.1.0",
  "sample_rate": 48000,
  "bpm": 124.0,
  "time_signature": [4, 4],
  "snap": { "enabled": true, "division": "1/16", "triplet": false },
  "hrtf": { "kind": "builtin", "id": "sadie-d1" },
  "distance": { "rolloff": 1.0, "min_distance": 0.2, "ref_distance": 1.0 },
  "master": { "gain_db": 0.0, "limiter_on": true },
  "media_pool": [
    {
      "id": "m-3f2a91c7", "path": "samples/kick.wav", "name": "kick.wav",
      "source_rate": 44100, "channels": 1, "frames": 12480,
      "hash": "sha256:9c1d…"
    }
  ],
  "channels": [
    {
      "id": "c-7a1f08e3", "name": "Kick", "color": "#A855F7",
      "gain_db": -3.0, "mute": false, "solo": false,
      "hrtf_bypass": false, "pan": 0.0,
      "snap_override": null,
      "position": { "x": 0.0, "y": 1.5, "z": 0.0 },
      "automation": {
        "pos.x": { "keyframes": [
          { "t": 0,      "value": -2.0, "interp": "ease",
            "handles": { "out": [24000, 0.0] } },
          { "t": 192000, "value":  2.0, "interp": "linear",
            "handles": { "in": [-24000, 0.0] } }
        ]}
      },
      "clips": [
        {
          "id": "k-2b08ff41", "media_id": "m-3f2a91c7",
          "start": 0, "offset": 120, "length": 11000, "gain_db": 0.0,
          "fade_in":  { "length": 64,  "shape": "linear" },
          "fade_out": { "length": 512, "shape": "equal_power" }
        }
      ]
    },
    {
      "id": "c-4d9c65ba", "name": "Backing mix", "color": "#22D3EE",
      "gain_db": 0.0, "mute": false, "solo": false,
      "hrtf_bypass": true, "pan": 0.0,
      "snap_override": null,
      "position": { "x": 0.0, "y": 1.0, "z": 0.0 },
      "automation": {},
      "clips": [
        {
          "id": "k-8e1d3c07", "media_id": "m-9e40b2d1",
          "start": 0, "offset": 0, "length": 5760000, "gain_db": 0.0,
          "fade_in":  { "length": 0, "shape": "linear" },
          "fade_out": { "length": 0, "shape": "linear" }
        }
      ]
    }
  ]
}
```

The second channel is the motivating case: a finished stereo stem that should
reach the output exactly as it was authored, with the spatial mix built around
it.

## Caches, not project data

One **user-level** cache directory, safe to delete at any time, never
committed and never beside the project (D-59):

| Platform | Location |
|---|---|
| Linux | `$XDG_CACHE_HOME/3dimmersive`, default `~/.cache/3dimmersive` |
| macOS | `~/Library/Caches/3dimmersive` |
| Windows | `%LOCALAPPDATA%\3dImmersive\Cache` |

- Peak pyramids per media file, keyed by content hash.
- Decoded + resampled audio, if we later decide re-decoding on load is too slow.
- Prepared HRTF banks (ITD + minimum-phase + FFT), keyed by SOFA hash and
  block size. Preparing a bank takes a second or two; caching it makes project
  load feel instant.

Every one of those is keyed by the hash of its *input*, so none of it is
specific to a project — which is why an earlier `.3dim-cache/` beside the
project was wrong twice over. Two projects using the same sample each computed
their own peak pyramid, against F-9's "computed once per file"; and a project
that has never been saved has nothing to sit beside, so the first import into
a new project had nowhere to write.

### The autosave sidecar

Not a cache, and not project data either: `<project>.3dim.recover`, written
beside the project while it has unsaved changes and removed on a clean save or
a clean exit (F-49, D-64). An unsaved project's sidecar goes to the cache
directory above, for exactly the reason the caches moved there.

It is a **sidecar and never the project file**. Autosave that rewrites the
project in place is the one form of it that can lose work rather than save it,
and it breaks the promise that `Ctrl+S` is the moment a decision becomes
permanent. Finding one on startup offers a recovery; it never loads silently.
