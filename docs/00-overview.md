# 00 — Overview

## What this is

A desktop application for composing music and sound design **in 3D space**. You
arrange audio samples on a timeline the way you would in any DAW, but each
channel also has a *position around the listener's head*. That position can be
animated with keyframes. The result is rendered binaurally — a stereo file that,
on headphones, places every sound at a specific point in space.

It is deliberately **not** a general-purpose DAW. There is no mixing console, no
plugin hosting, no MIDI, no recording. The one thing it does that a DAW does
badly is make spatial placement a first-class, visual, animatable property.

## Who it's for

Producers and sound designers making headphone-first material: binaural mixes,
ASMR, spatial ambiences, game/film pre-vis, and music that moves around you.

## The core loop

1. Create a project, import audio into the media pool.
2. Drag a sample onto a timeline channel. The channel has a colour.
3. An icon in that colour appears around the head in the spatial workspace.
4. Drag the icon to place the sound. Add keyframes to make it move.
5. Set BPM and snap, trim clips so they line up.
6. Render to a binaural stereo WAV.

## Platform & stack

| | |
|---|---|
| Language | Python 3.11+ |
| UI | PySide6 (Qt 6) |
| DSP | numpy + scipy |
| Audio I/O | sounddevice (PortAudio) |
| File I/O | soundfile (libsndfile), soxr (resampling) |
| HRTF | SOFA datasets via `sofar` |
| Targets | Windows, macOS, Linux |

See [02-architecture.md](02-architecture.md) for why Python, and where the
escape hatch to a native engine sits if we ever need it.

## In scope for v1

- Media pool, non-destructive clip editing (trim, crop, fades, gain)
- Multi-channel timeline with BPM grid, snap, per-channel snap override
- Full 3D positioning: azimuth, elevation, distance
- Keyframe automation of position and gain with a curve editor
- Per-channel HRTF bypass, for stems and material that must stay as-authored
- Realtime binaural preview
- Offline binaural render to WAV, plus optional per-channel stems
- Project save/load, full undo/redo

## Explicitly out of scope

| Not doing | Why |
|---|---|
| Reverb / room simulation | Large scope, own tuning UI. Dry HRTF only. |
| Moving/rotating listener | Sources move; the head stays at origin. |
| VST hosting or plugin export | Would have forced C++. Ruled out deliberately. |
| MIDI, recording, instruments | This is an arranger, not a DAW. |
| Time-stretch / pitch-shift | v1 clips play at native rate. |
| Ambisonic or multichannel output | Binaural stereo only. |
| Tempo changes | One global BPM. |
| Head tracking | No. |
| Air absorption over distance | Cheap and effective, but deferred. See D-22. |
| Per-channel HRTF *sets* | Mixing datasets in one mix sounds inconsistent. See D-20. Bypassing HRTF per channel is supported — that is D-32, a different thing. |
| Video file export of the 3D view | Screen recording covers v1. See D-24. |

## Later, maybe

Ordered roughly by how much they'd be missed:

- Video/animation export of the 3D view (the read-only 3D view exists partly for
  this — see [04-ui-spec.md](04-ui-spec.md))
- Room reverb and early reflections
- Ambisonic (B-format) export alongside binaural
- Tempo map
- Per-listener HRTF personalisation beyond just picking a SOFA file
- Motion path presets (orbit, flyby, random walk), and with them **orbit
  interpolation** — interpolating azimuth and radius instead of cartesian
  coordinates, so a source crossing from left to right arcs around the
  listener instead of passing through their head (see
  [03-data-model.md](03-data-model.md))
