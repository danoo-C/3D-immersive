# M2 · Phase 6 — The media pool

**Status:** ✅ complete · **Plan:**
[plans/phase_6_media_pool.md](plans/phase_6_media_pool.md)

## Goal

File › Import Audio… takes files or a folder and fills the explorer's media
pool: a tree of what was imported, each row with its name, duration and
waveform thumbnail, a filter box above it, and rows that can be dragged. The
decoding happens off the UI thread, every file that could not be read is
reported, and the whole import is one edit that one Undo takes back.

This is the phase the milestone's acceptance can first be seen in, short of
the sound.

## Scope

**In:** importing files and folders, a folder recursively; decode, hash and
peaks on workers so the window keeps responding (N-3); the command that adds
media to the pool, one per import; the tree, mirroring the folders beneath
what was imported; the filter; each row's name, duration and thumbnail; the
drag *source*, and the MIME type it carries, named in `04` so M3 can accept
it; missing files drawn in `warn`; importing the same audio twice; the theme
groups `04` gives M2 — tree view, header and filter field.

**Out:** the drop target → M3. The relink action on a missing row → M8,
before beta. Removing media from the pool — the plan decides whether it
belongs here; nothing in the acceptance needs it. The parameters pane's media
view, which arrives with the pane.

## Acceptance

- [x] Importing a folder of *n* readable files adds *n* `MediaFile`s in one
      undoable step. One Undo removes all *n*; Redo restores them without
      decoding again.
- [x] The tree mirrors the folder structure beneath the imported folder.
- [x] Each row shows its name, duration and waveform thumbnail.
- [x] The filter narrows rows by name, ignores case, and keeps the folders
      that lead to a match.
- [x] During the import of a folder large enough to take seconds, the UI
      thread keeps turning — asserted by a timer that keeps firing, not by
      the import merely finishing.
- [x] A file that cannot be decoded is not added, and the import posts **one**
      notice whose detail lines name each failure and its reason.
- [x] Importing audio already in the pool does what the plan decides, and
      says so rather than silently adding a duplicate.
- [x] Dragging a row produces the MIME type `04` names, carrying the media's
      id.
- [x] The groups tree view, header and filter field are in `04` and the
      bundled theme, and no widget in the pool names a hex.
- [x] A screenshot of a real imported folder is taken and looked at.

## Implements

F-3, F-4, F-5, F-7, F-9, F-56, N-3 — *Media pool* in
[04-ui-spec.md](../04-ui-spec.md).

## Notes

Appended while building.

**Everything the first five phases built, on screen and joined up.** A
folder imports on workers as one undoable edit; the pool shows its folders,
its samples' lengths and their waveforms; a filter narrows it; and a row
drags as `application/x-3dimmersive-media` for M3 to accept.

### Four layers, each testable without the next

Preparing one file (`core/media_store.py`, headless), keeping what was
prepared (`MediaStore`, by media id, for the session), importing on workers
(`ui/importer.py`), and the pool itself. The admission rules — fresh ids,
refusals set aside, duplicates refused under any name (D-93) — live in
`core` and are tested without a window; the window's import handler is a
dozen lines that call them.

The store is what makes Redo of an import free: undoing takes the entries out
of the pool and leaves their audio in the store, so Redo puts back what is
already decoded. It is also where phase 7's audition will read from.

### Found while building: a reopened project had no samples

The plan filled the store only from imports. A project saved and reopened
showed blank thumbnails and, at phase 7, would have played nothing. Opening
now prepares the samples that are present on a second importer, into the
store and not the model — no edit, no dirty mark, no hash written (D-89). The
saved hash earns its keep a second time here: a file changed since the
project was saved is reported by comparing it with the one just computed.

### Two hazards designed out before they could bite

A job that raised would never deliver, and its import would wait forever, so
a job turns anything unexpected into a refusal. And a person can open another
project while workers run, so both the importer and the loader remember which
project they were for, and results for one that is no longer open are set
aside rather than added to the wrong project. Both have tests; both would
otherwise be one-in-fifty bugs.

### D-93, and one rule the plan did not have

Only F-5's suffixes are tried, so a readme passes without a word. Building
`find_audio` added a second rule: **hidden files are passed over too**,
because macOS leaves an AppleDouble `._kick.wav` beside every `kick.wav` on
any drive it has touched, carrying the suffix without the audio.

### Found by looking

The grab of a real imported kit — drums, FX and pads, a readme ignored, a
broken WAV as one line of one notice — showed what no test could: three
fixed-width columns in a 250 px panel squeezed the thumbnail to a 35 px
smear, truncated the lengths and scrolled sideways. The name now takes what
is left, the length is compact (`1.40s`, `3:12`) and sized to its contents,
the waveform has a fixed 72 px and no title, and nothing scrolls sideways.

### M9's golden fixture, retired

It proved M9 phase 1's indirection changed no pixel of the stylesheet, and
said in its docstring that it would retire the first time a milestone
legitimately changed the sheet. This phase added the pool's rules. A golden
file regenerated on every rule records whatever the code does, which is not a
test of anything, so it went.

### What the mutation sweep found

Eighteen mutations — the plan's thirteen, two restated because the code as
built could not make them literally, and five for what building added: the
load and import guards, hidden files, and clearing the store. **None
survived.**
