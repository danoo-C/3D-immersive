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
├── id               uuid
├── path             relative to the project file
├── name
├── source_rate      as found on disk
├── channels         1 or 2 (stereo is downmixed at play time)
├── frames           length at project rate, after resampling
└── hash             for relink and cache invalidation

Channel
├── id, name, index
├── color            hex, from the channel palette
├── gain_db, mute, solo
├── hrtf_bypass      bool   true → straight to the stereo bus, unprocessed
├── pan              float  -1 left … 0 centre … +1 right; bypass only
├── snap_override    null → inherit Project.snap
├── position         { x, y, z }            used where no automation exists
├── automation       { "pos.x": Curve, "pos.y": Curve, "pos.z": Curve,
│                      "gain": Curve, "pan": Curve }   any key may be absent
└── clips            [Clip]                 sorted by start, never overlapping

Clip
├── id
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

### Rules

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
- `pan` is meaningful only under bypass. On a mono source it is a
  constant-power pan; on a stereo source it is a balance, attenuating the
  opposite side rather than folding the image.

### Evaluating a curve

`Curve.value_at(t)` finds the bracketing pair and interpolates:

- `hold` — the left keyframe's value until the right one.
- `linear` — straight line.
- `ease` — cubic bezier defined by the two keyframes and their facing handles,
  solved for `t` then evaluated for value. Handle `dt` is clamped so the curve
  can never double back in time.

The engine calls this once per channel per parameter per block.

## Project file

`.3dim` — UTF-8 JSON, pretty-printed with sorted keys so it diffs cleanly in
git. A `schema_version` integer drives forward migration on load. Fields added
later default on read — a project written before `hrtf_bypass` existed loads
with it `false`, which is the previous behaviour.

```json
{
  "schema_version": 1,
  "sample_rate": 48000,
  "bpm": 124.0,
  "time_signature": [4, 4],
  "snap": { "enabled": true, "division": "1/16", "triplet": false },
  "hrtf": { "kind": "builtin", "id": "sadie-d1" },
  "distance": { "rolloff": 1.0, "min_distance": 0.2, "ref_distance": 1.0 },
  "master": { "gain_db": 0.0, "limiter_on": true },
  "media_pool": [
    {
      "id": "m-3f2a", "path": "samples/kick.wav", "name": "kick.wav",
      "source_rate": 44100, "channels": 1, "frames": 12480,
      "hash": "sha256:9c1d…"
    }
  ],
  "channels": [
    {
      "id": "c-01", "name": "Kick", "index": 0, "color": "#A855F7",
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
          "id": "k-01", "media_id": "m-3f2a",
          "start": 0, "offset": 120, "length": 11000, "gain_db": 0.0,
          "fade_in":  { "length": 64,  "shape": "linear" },
          "fade_out": { "length": 512, "shape": "equal_power" }
        }
      ]
    },
    {
      "id": "c-02", "name": "Backing mix", "index": 1, "color": "#22D3EE",
      "gain_db": 0.0, "mute": false, "solo": false,
      "hrtf_bypass": true, "pan": 0.0,
      "snap_override": null,
      "position": { "x": 0.0, "y": 1.0, "z": 0.0 },
      "automation": {},
      "clips": [
        {
          "id": "b-01", "media_id": "m-9e40",
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

Kept beside the project in `.3dim-cache/`, safe to delete, never committed:

- Peak pyramids per media file, keyed by content hash.
- Decoded + resampled audio, if we later decide re-decoding on load is too slow.
- Prepared HRTF banks (ITD + minimum-phase + FFT), keyed by SOFA hash and
  block size. Preparing a bank takes a second or two; caching it makes project
  load feel instant.
