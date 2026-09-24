# Plan — M2 · Phase 7 — Audition

**Written:** 2026-09-24 · **Status:** in progress

## Approach

Deliberately trivial, as the roadmap says, and deliberately honest about the
one thing that is not: the first sound is the first dependency on a machine's
audio stack, and that stack may be missing, may not have the device asked
for, and may refuse 48 kHz.

**The audio backend is a parameter.** `audio/device.py` loads `sounddevice`
lazily, when first asked, and returns either the module or the reason it
could not be loaded. Everything that plays takes a backend object with the
three things it needs — `OutputStream`, `CallbackStop`, `query_devices` — so
the tests hand it a stand-in and drive its callback block by block. Nothing in
the suite needs PortAudio or a device, and nothing depends on whether the
machine running it has either.

**Importing `sounddevice` is not allowed to stop the application starting.**
It raises `OSError` at import on a Linux machine without PortAudio — this one,
and CI's runner before this phase. So it is never imported at module level
anywhere; the application starts, audition says why it is unavailable, and
one notice says what to install.

**`audio/` stays Qt-free**, as `core/` is, though no rule demands it yet: the
audition object reports problems through a plain callback, and the window
turns that into a notice on the UI thread. PortAudio's callback thread must
never touch a widget, and a Qt-free module cannot.

## The one mechanism worth spelling out

The callback copies the next block of the sample into the output: stereo as
it is, mono into both ears, silence past the end and then `CallbackStop`. A
second double-click **replaces** what is playing by swapping one reference
the callback reads each block — a single attribute assignment, which is
atomic under the GIL — rather than stopping and reopening the stream.

## Steps

1. **The flags and the backend.** `--device` and `--block` parsed in
   `__main__`, reaching `app.run`; `audio/device.py` with the lazy backend and
   the checks — device exists, block in 256–2048, 48 kHz accepted. A bad flag
   is a notice and a default, not a refusal to start (F-56).
   *Test:* flags parse; an unknown device, a block out of range and a device
   refusing 48 kHz each become one notice and a working default; loading the
   backend never raises, whatever the machine has.

2. **The audition.** `audio/audition.py`; the pool's double-click; the
   window's `audition(media_id)`; rows' tooltips saying how to hear them, or
   why they cannot be heard. CI installs `libportaudio2`; `08` says to.
   *Test:* against a stand-in stream opened at 48000 Hz only; the callback
   writes the sample's frames in order, mono in both ears, then silence and
   `CallbackStop`; a second sample replaces the first from its own first
   frame; with no backend the application starts, the tooltip says why, and
   one notice says what to install; a device lost mid-sample is one notice.

3. **Heard.** On native Windows or Linux, by a person: a 44.1 kHz WAV and an
   MP3, at the right pitch and speed. Recorded in the Notes with the machine,
   device and block size. This cannot be done on WSL and is not done by this
   plan's author.

## Files

```
docs/08-environment.md             amended — PortAudio on Linux
docs/m2_media/phase_7_*.md         amended — Notes
.github/workflows/ci.yml           amended — libportaudio2
src/immersive/__main__.py          amended — the flags
src/immersive/app.py               amended — the backend, the audition
src/immersive/audio/device.py      new
src/immersive/audio/audition.py    new
src/immersive/ui/main_window.py    amended — audition, notices
src/immersive/ui/explorer/media_pool.py   amended — double-click, tooltips
tests/test_audition.py             new
tests/test_flags.py                new
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| Stand-ins that behave unlike PortAudio | tests that pass and a sample that does not play | the stand-in implements only what `sounddevice` documents — samplerate, blocksize, device, callback signature, `CallbackStop` — and step 3 is a person listening |
| The callback thread touching Qt | a crash that happens under load | `audio/` imports no Qt, asserted, and problems cross by a queued signal |
| A device lost mid-sample | a stream that stops with nothing said | `finished_callback` reports, and the window posts it on the UI thread |
| This phase cannot be finished here | a milestone marked complete that nobody heard | the last acceptance box stays unticked until a person ticks it, and M2 is not marked complete before |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| the stream opened at the device's rate | a silent resample, or 44.1 kHz material eight percent fast |
| mono into one ear | half a sample |
| the end not silenced | the last block's garbage, repeated |
| the stream not stopped at the end | a stream left running for nothing |
| a replacement continuing from the old position | the second sample starts part-way through |
| an unknown device refusing to start | the wrong default device and no way out, which is D-63's reason |
| `sounddevice` imported at module level | no PortAudio, no application |
| `--block` ignored | the flag exists and does nothing |
| a lost device said nowhere | the stream stops and nothing says why |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| Transport, mixing, gain, the engine | M3 |
| Spatialisation | M4 |
| Device and block size in Preferences | M8, after beta |
| The live xrun counter | M3 |
| An audition button in the parameters pane | when the pane arrives |

## Outcome

Filled in at the end.
