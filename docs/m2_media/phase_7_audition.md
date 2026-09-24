# M2 · Phase 7 — Audition

**Status:** built and tested — **waiting to be heard** · **Plan:**
[plans/phase_7_audition.md](plans/phase_7_audition.md)

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

- [x] `python -m immersive --device <name> --block <n>` is parsed, and a
      device that does not exist is reported while the application still
      starts.
- [x] The stream is opened at 48000 Hz whatever the device prefers, asserted
      against a stand-in for the stream. A device that refuses is a notice,
      never a silent fallback to another rate ([05](../05-audio-engine.md),
      *The output stream*).
- [x] Driven block by block through a stand-in, the callback writes the
      sample's frames in order, puts a mono sample in both ears, and after
      the last frame writes silence and stops.
- [x] Double-clicking a second sample while one plays replaces it.
- [x] With no PortAudio, the application starts, audition is disabled with the
      reason in its tooltip, and one notice says what to install.
- [x] CI installs what Linux needs, and `08`'s setup names it.
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

**Built, tested against a stand-in, and not yet heard.** Six of the seven
boxes are settled by tests. The seventh is a person listening on native
Windows or Linux, and it stays open until one has — this machine is WSL and
has no PortAudio, which is exactly the case the phase had to handle
gracefully, and did.

### ⚠️ To tick the last box

On a native Windows or Linux machine, with headphones:

1. On Linux, `sudo apt install libportaudio2`. Windows needs nothing extra.
2. `python3 launch.py --install --run` — or, with a device or block size in
   mind, `python3 launch.py --install --run -- --device "Headphones" --block 512`.
3. File › Import Folder…, and pick a folder with a 44.1 kHz WAV and an MP3.
4. Double-click each. Both should play at their own pitch and speed — a
   44.1 kHz file played without resampling would be eight percent fast and
   sharp by about a semitone and a half.
5. Record here the machine, the device, the block size and what was heard,
   then tick the box — and M2 can be marked complete.

### What a real launch does on a machine without audio

Checked by hand before it was tested: on this machine the application
starts, cannot be heard, and posts one notice naming `libportaudio2`. The
pool's rows say *Cannot be heard* and why. `--device` and `--block` are not
judged at all without a backend — there is nothing to ask about devices — so
a wrong value on such a machine goes unreported until PortAudio is there.

### The stream, and the replacement that cannot lose a sample

Opened at 48 kHz and nothing else; a device that will not do 48 kHz is said
and not worked around, because 05 allows no output resampler. A second
double-click replaces the first by swapping one reference the callback reads
each block. The one subtle part is the moment the callback has decided to
stop: it announces that it is stopping *before* it checks whether the sample
changed, and the window checks the announcement *after* it swaps — so in any
order of the two threads, either the callback sees the new sample and plays
it, or the window sees the stream stopping and reopens it. The comments in
`audio/audition.py` carry the argument where it applies.

### What the mutation sweep found

Eleven mutations, ten killed on the first run. The survivor was the seam
between parsing the flags and running with them: `parse` and `app.run` each
had tests, and the line joining them in `main` could drop both flags
unnoticed. Importing `sounddevice` at module level was killed at collection
on this machine; on CI, which now installs PortAudio, the test that walks
the package's module-level imports is what catches it.
