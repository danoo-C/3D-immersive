# Plan — M3 · Phase 9 — Transport

**Written:** 2026-09-26 · **Status:** ✅ complete

## Approach

Four layers.

**The engine learns to play and to stop, to loop, and to audition**
(`audio/engine.py`). Playing, the loop region and the loop switch arrive
through the ring, as commands ordered with seeks. Stopped, `process()`
leaves the playhead where it is and plays no clip, but still drains the
ring and still plays an audition. A block that crosses the loop's end is
rendered in pieces, the playhead wrapping to the loop's start between
them. An audition is a voice summed into the bus after the channels: one
decoded sample, played from its first frame to its last. All of this is
tested block by block, headless, as phase 8 was.

**A player owns the one stream** (`audio/player.py`, replacing
`audio/audition.py`). It opens the stream the first time anything is to
be heard and keeps it open (D-107). It gives the window play, pause,
stop, seek, loop and audition, and reports a device that goes. It holds
every audition voice it hands the engine until the engine has let go of
it, as the feed does snapshots, so no decoded array is freed on the audio
thread. M2's audition tests move to it, against the same stand-in
backend.

**The loop region joins the model** (D-108): `Project.loop`, a start and
an end or nothing, saved in the `.3dim` and set through `SetAttribute`.
The ruler gets its three gestures (D-109): drag the playhead, draw a loop,
click to seek. It also draws the region, and the lanes draw it faintly
behind the clips.

**The window becomes a transport.** The Transport menu, the toolbar's
buttons and `Space`, `Esc`, `Enter` and `L` are live. The playhead readout
is a numeric field in the ruler's unit. A timer at 30 Hz reads the
engine's playhead into the timeline, turns the page when it leaves the
view (D-110), and reads the xrun count into the status bar.

The alternative for the stream was to keep M2's audition on a stream of
its own and give the transport another, closing each when idle. It was
rejected (D-107): two streams on one device are refused by some backends,
and a stream that closes when idle leaves the ring undrained while
stopped.

## Decisions settled here

**One stream (D-107).** This is the question the milestone left here.
Audition is summed into the bus over the arrangement, so a double-click
during playback is heard over it. The stream opens on first use and stays
open. A lost device stops the transport, holds the playhead and posts one
notice. The next Play or double-click reopens it.

**The loop region is the project's; the switch is the transport's
(D-108).** Drawing a region turns looping on. A region is at least 64
samples long. A playhead past the region's end plays on and does not jump
back, as in every DAW; one before it plays into the region and then
loops.

**The ruler's gestures (D-109).** The other question this phase was given.
A press within 5 px of the playhead takes it, and dragging moves it,
seeking as it goes while playing. A press elsewhere that moves draws a
loop region; one that does not move seeks. All three snap to the grid and
to clip edges by the project's setting, and `Alt` places exactly.

**Pause and stop (D-110).** `Space` plays and pauses. `Esc` stops back to
where playback started, and with the transport already stopped clears the
selection, keeping phase 4's rule. `Enter` goes to 0. The page turns when
the playhead leaves the view.

**What the playhead shows.** The engine's playhead is where its next block
starts, which is ahead of what is heard by the stream's latency. At a block
of 512 that is about 11 ms, under a frame at 60 Hz, so it is shown as it is
and not compensated. If phase 10's listening says otherwise, the stream's
own latency figure is the correction.

**A seek while stopped.** The stream, once open, drains the ring while
stopped, so a seek is a command like any other. Before the stream has
ever opened there is no audio thread, so the player applies the engine's
commands itself: nothing else can be reading them.

## Steps

1. **The engine plays, stops, loops and auditions.** Commands for play,
   and for the loop region with its switch. A stopped engine leaves the
   playhead and plays no clip. A block crossing the loop's end is rendered
   in pieces. An audition voice is summed into the bus.
   *Test (headless):* stopped, the playhead holds and the bus is silent;
   played, it moves; a loop runs from its start to its end and on from its
   start with no gap and no repeated sample, at blocks of 256, 512 and 2048
   and with a loop shorter than a block; a playhead past the loop plays on;
   a gain ramps across a wrapped block; the audition voice plays from its
   first frame, mono to both ears, is silent after its last, is replaced by
   the next from its first frame, and is heard over the arrangement; the
   allocation test covers looping and the voice.

2. **The player: one stream.** `audio/player.py` opens the stream on first
   use at 48 kHz with the settled device and block, and routes its
   callback to the engine. Transport and audition calls go to the engine.
   A device lost or refused is reported, and the transport stops. Voices
   are held until the engine lets go. `app.py` builds it, the window takes
   it, and `audio/audition.py` goes.
   *Test (stand-in backend):* the stream's settings, once; the flags reach
   it; audition frames in order and mono to both ears; a second sample
   replaces the first; the stream stays open after a sample ends; a refused
   device and a lost one each reported once; a lost device stops the
   transport and holds the playhead; commands before the stream opens are
   applied; the window's double-click plays and says why it cannot.

3. **The loop region, and the ruler's gestures.** `Project.loop` in the
   model, `validate()` and the file. The ruler's press, drag and click
   (D-109), snapping, and the region drawn in the ruler and behind the
   lanes (`timeline.loop.region`).
   *Test:* a region survives a save and a reopen, and a file without one
   opens; one shorter than 64 samples or backwards is refused; dragging the
   playhead moves it and starts no region; drawing a region moves no
   playhead and is one Undo; a click seeks; each snaps, and not with `Alt`;
   the region is drawn in its colour.

4. **The window as a transport.** Actions and keys, the toolbar's buttons,
   the readout, the 30 Hz timer, page turning, the xrun count, the device
   notice, `Esc`'s two meanings, the feed wired to the document and the
   loaded samples, and no tooltip naming M3.
   *Test (stand-in backend):* `Space`, `Esc`, `Enter` and `L`, asserted on
   what the engine is asked and on the blocks the stand-in receives; the
   drawn playhead is the engine's after a tick; the page turns; a position
   typed in the readout in either unit seeks; the xrun count is quiet at
   zero and `error` after one; a lost device stops, holds and posts one
   notice; a double-click during playback is heard over it; an edit during
   playback is heard at the next block; `Esc` while stopped clears the
   selection; no tooltip names M3.

5. **Written down, and looked at.** `04`'s *Timeline* (the ruler's three
   gestures, the loop region), *Transport*, *Keyboard*, and *Accessibility
   and feel* (the xrun count's colours); `03` for `Project.loop` and the
   file; `05`'s *The output stream* (one stream, opened on first use);
   `02`'s module map. A grab of a loop drawn and playing, with the playhead
   inside it.

## Files

```
docs/01-requirements.md                     amended — four decisions
docs/02-architecture.md                     amended — player.py
docs/03-data-model.md                       amended — Project.loop, the file
docs/04-ui-spec.md                          amended — ruler, transport, keys
docs/05-audio-engine.md                     amended — one stream
docs/doc-system.md                          amended — high-water mark
src/immersive/audio/engine.py               amended — play, loop, voice
src/immersive/audio/player.py               new — the one stream
src/immersive/audio/audition.py             removed — into the player
src/immersive/app.py                        amended — builds the player
src/immersive/core/model.py                 amended — LoopRegion, validate()
src/immersive/core/io/project_io.py         amended — the loop in the file
src/immersive/ui/timeline/ruler.py          amended — gestures, the region
src/immersive/ui/timeline/view.py           amended — the region behind the lanes
src/immersive/ui/timeline/panel.py          amended — seeks go out
src/immersive/ui/main_window.py             amended — the transport
src/immersive/assets/themes/vscode_dark.3dimtheme   amended — loop.region
tests/test_engine.py                        amended
tests/test_realtime.py                      amended
tests/test_player.py                        new — was test_audition.py
tests/test_transport.py                     new — gui
tests/test_ruler.py                         new — gui
tests/test_project_io.py                    amended
tests/test_theme_io.py                      amended — loop.region arrives
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A wrap that drops or repeats a sample | a click at every loop | the loop test compares the stand-in's samples with the source, end to start, at three block sizes and with a loop shorter than a block |
| A voice's array freed on the audio thread | a destructor in the callback | the player holds every voice it hands over until the engine lets go, as the feed does snapshots |
| The timer's playhead moving the clips' preview or selection | a drag in progress disturbed at 30 Hz | the timer sets the playhead only, which draws a line; the view's drag state is untouched, and a test drags during playback |
| A seek from the timer's own update | the playhead jumping back a frame, as the readout's write reads as a typed seek | the readout's `set_value` commits nothing, as phase 2 made it; only a person's commit seeks |
| Transport keys in text fields | `Space` in a channel's name starting playback | a line edit claims printable keys; tested as `S` was |
| A device lost with no audio thread left | a stuck transport | `finished_callback` runs on PortAudio's thread; the player posts through a signal-safe callback, as M2's audition did, and the window stops the transport on the UI thread |
| Timer ticks in tests | flaky timing | the tick is a method the tests call directly; the timer only calls it |
| The engine's playhead read while it is being written | a torn read | a Python attribute read is atomic under the GIL |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| a stopped engine moving the playhead | pause does not hold |
| a stopped engine still playing clips | the arrangement heard while stopped |
| the loop wrapping one sample late | a repeated sample at the join |
| the loop wrapping to 0, not its start | the wrong material |
| a playhead past the loop jumped back | the loop pulls it in |
| the voice under the channels' gains | a muted channel silences an audition |
| a voice replaced mid-block from its middle | not from its first frame |
| a voice dropped by the engine | freed on the audio thread |
| the stream closed after a sample | the ring left undrained while stopped |
| a lost device not stopping the transport | a playhead the timer keeps moving |
| a lost device reported twice | two notices for one loss |
| the loop region not saved | a region gone on reopening |
| a backwards region accepted | a loop the engine cannot play |
| a press on the playhead drawing a loop | D-109 broken |
| a drawn loop moving the playhead | D-109 broken |
| the ruler snapping by a channel's setting | an override that is not the ruler's |
| stop not returning to where play started | stop and pause the same |
| `Esc` while stopped not clearing the selection | phase 4's rule lost |
| the page turning while stopped | the view jumping under a click |
| the xrun count never turning `error` | dropouts hidden |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The master meter | phase 10 |
| Scrubbing: the audio under a dragged playhead | not planned (the phase's *Out*) |
| Moving a drawn loop region's edges, or the region as a whole | not planned; draw it again. Raised if missed |
| Latency compensation of the drawn playhead | not planned; revisited if phase 10's listening shows it |
| Rendering the loop region | M7 (F-53) |
| A count-in, a metronome, record | not in any requirement |

## Outcome

Five steps in the planned order, and all ten acceptance boxes are ticked.
Sixty-six mutations: sixty-two killed, and four that found code with no
effect, which is gone. Nineteen of the twenty named in advance were run as
named, the last of them - "the ruler snapping by a channel's setting" - with
a test written for it at the end. "The voice under the channels' gains" was
not, since no line has that shape; a test mutes a channel under an audition
and hears the audition. 2094 tests.

⚠️ **The step commits' mutation counts are wrong**: 18, 12, 20 and 21 where
the lists run were 16, 11, 18 and 20. They were counted from memory rather
than from the lists. The totals above are counted from the lists.

### What the plan got right

**The engine first, headless.** Looping, stopping and the voice were
settled block by block, including a loop shorter than a block, before any
window touched them. The window's loop test then passed first time.

**The player as the only owner of the stream.** A device's loss is a flag
on PortAudio's thread and everything else happens on the UI thread, so
the player stayed Qt-free and the window's part is one call a tick.

**Seeks through the ring, with a mark.** `sent()` and `caught_up()` let
the tick ignore a playhead from before a seek, which the plan's risk table
had named.

### What the plan did not see

**Enter and Esc.** A line edit claims the keys that type, but not those
two, and they became the transport's the moment Stop and Return to Start
were live. The fields that commit or cancel, and the clip drag, now claim
them.

**A phase 8 bug**: a snapshot's levels were what it was built with, not
its targets as taken up.

**A flaky test**, whose failures made three mutations look caught.

**Code with no effect.** In the player, a flag cleared twice, a closing
flag the stream check made redundant, and a stop after a refused open that
nothing had started. In the window, a guard on the page turn that only
decided a pause between two ticks, where following the engine is better.

**A test harness that hung.** A test that runs `app.run` raised inside the
event loop and never quit; its callback now quits in a `finally`.

### Deviations

| Planned | Actual |
|---|---|
| `tests/test_player.py` new | `test_audition.py` renamed to it, and the stand-in moved to `tests/standin.py` |
| No new widget | `ui/widgets/text.py`, a line edit that keeps Enter and Esc |
| The page turns while playing | whenever the engine moves the drawn playhead - which is while playing, and the blocks before a pause |
| Twenty mutations | sixty-five |

### What phase 10 needs to know

- **Peaks:** `engine.take_peaks()` gives the bus's highest level per side
  since the last call. The window's tick at 30 Hz is where a meter reads
  it. Hold and decay are the meter's.
- **Where the meter goes:** the status bar has the xrun count, the
  notices and the version; the meter goes left of the notice count
  (`04`).
- **The listening test:** it can now cover the arrangement, audition over
  it and a loop, on native Windows or Linux, in one sitting with M2's.
- **Latency:** the drawn playhead is the engine's next block, not what is
  heard. Listening may say whether that needs the stream's latency figure
  as a correction.
- **Garbage collection:** `gc.freeze()` after a project loads is still not
  done. It belongs with the listening, where a pause would be heard.
