# a GRAPHICAL 3d sound creator
## how to use
- create a new project. add in sound files, anything, full songs or samples.
- select a sound file and drag it to the timeline. it will appear in the chanels color from the timeline (timeline has the chanels).
- click the channel and an icon the the chanels color appears around a head from the top wiew.
- you can move the icon around and it will project the sound in 3d space. (only works on headphones)
- do this for all samples and you have a full 3d mix of samples.
- optionally select the bpm of the song and the snap mode for easier sample alignment.
- also crop, cut the samples for them to align better.
- optinally disable snap mode on indiviadual chanels disregarding the global snap mode.
- and support for keyframes, so you can animate each chanel. basically you can assign keyframes to multiple chanels.


## how the app looks
- its look is minimalistic and the colors are dark with a spice of purple. 
- a resisable timeline part on the bottom of the window.
- a list of sample in an explorer on the left above the timelibe.
- the rest is the main workspace occupying the middle of the window. 
- and the right side of the window above the timeline is the keyframe explorer.
- a top menu bar.

## how the explorer looks
- explorer is spit into 2 parts, the main part on the top and middle, and the bottom part
- the bottom part is a resisable config/param

---

## documentation

Full specification, architecture and build plan live in [`docs/`](docs/).
Start with [`docs/00-overview.md`](docs/00-overview.md), or
[`docs/06-roadmap.md`](docs/06-roadmap.md) for the build order.

**Decided since this file was written:** Python (PySide6 + numpy + sounddevice),
cross-platform, realtime binaural preview, full 3D including elevation. A
channel is a track holding many clips. Keyframes are pinned to timeline time,
with Shift+drag to bring them along. Rationale for each is in
[`docs/01-requirements.md`](docs/01-requirements.md).

Two things above have since been **overruled**, and are left in place because
this file is the record of what was originally wanted:

- *"dark with a spice of purple"* — the surfaces are now VS Code's neutral
  greys and only the accent stays purple. The purple-black original read as a
  toy, and a purple playhead is more visible on grey than on purple-black
  (D-44).
- *"the rest is the main workspace occupying the middle"* — the workspace is
  two editable orthographic views (top X/Y and front X/Z) plus a read-only 3D
  view, and they are arranged as **two tabs** rather than side by side: three
  panes each took a third of the width, too narrow to place a source precisely
  in, and one of those thirds went to a view that cannot be dragged in at all
  (D-5, D-49).

⚠️ The "how the explorer looks" section above is **truncated mid-sentence**. The
missing text was never recovered; the pane has been specced as a
selection-driven parameters pane — a reconstruction, not a transcription. See
[`docs/07-qa-archive.md`](docs/07-qa-archive.md) QA-29.

Every question raised during spec review is answered and merged. The archive of
those questions and answers is [`docs/07-qa-archive.md`](docs/07-qa-archive.md).
