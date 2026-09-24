# M2 · Phase 7 — Audition

**Status:** not started · **Plan:** not written yet

## Goal

Double-clicking a sample in the pool plays it straight to the output at
48 kHz, without spatialisation. The device and the block size can be chosen
on the command line, and a device that will not open — or a machine with no
PortAudio at all — is reported rather than fatal. This is the first sound the
application makes, and the first use of `sounddevice`, kept deliberately
trivial.

## Scope

**In:** `audio/device.py` — opening an output stream at 48 kHz and nothing
else, enumerating devices, closing cleanly; `--device` and `--block`
(D-63), moved here from M3 because this is the first sound; the audition
player — mono to both ears, stereo as it is, silence and a stopped stream at
the end; a second double-click replacing what is playing; a device that
refuses 48 kHz, cannot be found or disappears mid-sample, each reported
through the notice centre; starting without PortAudio installed, with
audition disabled and the reason reported; what CI's Linux runner installs,
and what [08](../08-environment.md) tells a developer to install.

**Out:** the transport, mixing several sources, gain, the realtime graph and
its snapshot swap → M3. Spatialisation → M4. The live xrun counter → M3.
Device and block size in Preferences → M8, after beta.

## Acceptance

- [ ] `python -m immersive --device <name> --block <n>` is parsed, and a
      device that does not exist is reported while the application still
      starts.
- [ ] The stream is opened at 48000 Hz whatever the device prefers, asserted
      against a stand-in for the stream. A device that refuses is a notice,
      never a silent fallback to another rate ([05](../05-audio-engine.md),
      *The output stream*).
- [ ] Driven block by block through a stand-in, the callback writes the
      sample's frames in order, puts a mono sample in both ears, and after
      the last frame writes silence and stops.
- [ ] Double-clicking a second sample while one plays replaces it.
- [ ] With no PortAudio, the application starts, audition is disabled with the
      reason in its tooltip, and one notice says what to install.
- [ ] CI installs what Linux needs, and `08`'s setup names it.
- [ ] **Heard**, on native Windows or Linux rather than WSL: a 44.1 kHz WAV
      and an MP3 auditioned at the right pitch and speed, with the machine,
      device and block size recorded in the Notes. The milestone's own
      acceptance is that a person hears a sample, and only a person can tick
      this box.

## Implements

F-8, F-55, F-56, D-11, D-63 — *The output stream* in
[05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
