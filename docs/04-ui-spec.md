# 04 — UI Specification

## Layout

Dark, minimal, purple accent. Every boundary below is a draggable splitter; the
layout itself is fixed (D-15).

```
┌──────────────────────────────────────────────────────────────────────┐
│  File   Edit   View   Transport   Render   Help                      │
├──────────────────────────────────────────────────────────────────────┤
│  ⏮  ▶  ⏹  ↻     │  120.0 BPM  4/4  │  Snap 1/16 ▾  │  ⟲ ⟳  │  ● ARM │
├───────────────┬──────────────────────────────────┬───────────────────┤
│  MEDIA POOL   │           WORKSPACE              │  KEYFRAME EDITOR  │
│               │ ┌──────────┬──────────┬────────┐ │                   │
│  ▾ drums      │ │   TOP    │  FRONT   │   3D   │ │  ╭─╮              │
│    ▪ kick.wav │ │  (X / Y) │  (X / Z) │ (read) │ │ _╯ ╰──╮           │
│    ▪ hat.wav  │ │          │          │        │ │       ╰───        │
│  ▾ pads       │ │   (o_o)  │  ──o──   │  ╱o╲   │ │                   │
│    ▪ warm.wav │ │  o    o  │   (o)    │ (o_o)  │ │  ├──┼──┼──┼──┤    │
│               │ └──────────┴──────────┴────────┘ │                   │
├───────────────┤                                  │                   │
│  PARAMETERS   │                                  │                   │
│  (selection)  │                                  │                   │
├───────────────┴──────────────────────────────────┴───────────────────┤
│ 1     2     3     4     5     6     7     8     9    10    11        │
│ ●Kick  │ [kick]──[kick]────────[kick]──[kick]                        │
│ ●Pad   │ ────[warm──────────────────────]                            │
│ ●Hat   │ [h][h][h][h][h][h][h][h][h][h][h][h]                        │
└──────────────────────────────────────────────────────────────────────┘
```

Panel sizes, splitter positions, last project and window geometry persist
between sessions.

## Colour palette

| Token | Hex | Use |
|---|---|---|
| `bg-0` | `#0E0B14` | application background, deepest |
| `bg-1` | `#16121F` | panel surfaces |
| `bg-2` | `#1E1929` | headers, raised elements |
| `bg-3` | `#2A2338` | hover, selected row |
| `border` | `#332B44` | 1px separators, splitter handles |
| `text-hi` | `#E8E4F0` | primary text |
| `text-lo` | `#9A93AC` | labels, secondary text |
| `text-dim` | `#635C75` | disabled |
| `accent` | `#A855F7` | primary purple: playhead, focus, active toggle |
| `accent-dim` | `#7E3FF2` | pressed state |
| `accent-glow` | `#C77DFF` | hover, keyframe highlight |
| `warn` | `#F59E0B` | clipping, missing media |
| `error` | `#EF4444` | xruns, load failures |

### Channel palette

Assigned round-robin on channel creation, user-overridable. All chosen to stay
legible on `bg-1` and distinguishable from each other and from `accent`.

`#A855F7` `#22D3EE` `#F59E0B` `#34D399` `#F472B6` `#60A5FA` `#FB923C` `#A3E635`

A channel's colour is used for: its header chip, its clips, its icon in all
three spatial views, and its curves in the keyframe editor. That colour thread
is the main navigational aid in the app — it is the one visual rule to never
break.

## Media pool (left, top)

Folder tree of imported audio. Per row: name, duration, a one-line waveform
thumbnail. Filter box at the top.

- Double-click auditions the sample (non-spatial, straight to the output).
- Drag a row onto a timeline channel to create a clip.
- Drag onto empty timeline space to create a new channel holding it.
- Missing files show in `warn` with a relink action.

## Parameters pane (left, bottom)

Context-sensitive on the current selection. Resizable; collapsible to a strip.

| Selection | Shows |
|---|---|
| **Media file** | path, source rate, channels, duration, full waveform, audition button |
| **Channel** | name, colour swatch, gain, mute/solo, **HRTF bypass**, snap override, position X/Y/Z spinboxes (greyed when bypassed), pan (only when bypassed) |
| **Clip** | source, start, length, crop offset, gain, fade-in/out length and shape |
| **Nothing** | project settings: BPM, time signature, HRTF set, distance rolloff, master gain, limiter |

Numeric fields are drag-scrubbable and accept typed values with units.

## Workspace (centre)

Three panes side by side, each independently resizable.

### Top view — X / Y — editable

Looking straight down. Head glyph fixed at centre, nose pointing up-screen.
Concentric distance rings at 1 m intervals, labelled. Each channel's icon is a
filled circle in the channel colour; the selected channel's is ringed and
brought to front.

- Drag an icon → sets `pos.x` and `pos.y`.
- Scroll → zoom the metre scale. Middle-drag → pan.
- When a channel has position automation, its full path is drawn as a faint
  trail in the channel colour, with keyframes as small diamonds, and a bright
  dot showing where the source is *right now*.

### Front view — X / Z — editable

Looking at the listener from the front. Same head glyph, same icons, same
trails. Horizontal line at Z = 0 marks ear level.

- Drag an icon → sets `pos.x` and `pos.z`. Y is untouched.

### 3D view — read-only

Fixed isometric camera, no controls. Renders the head, all sources with their
motion trails, and a ground grid. It exists to read the whole scene at a glance
and to look good in screen recordings — hence the deliberate lack of controls
that could be knocked out of place mid-take.

Drawn with `QPainter` under an orthographic projection, not OpenGL: no extra
dependency, and it is not on a latency path. A real GL scene stays possible
later if we add video export.

### Bypassed channels

A channel with HRTF bypass has no position, so it is **not drawn on any of the
three canvases**. Pretending otherwise would put an icon somewhere it does not
mean anything, and parking every bypassed channel at the origin would pile them
into an unreadable heap.

Instead they appear in a **bypass strip** along the bottom edge of the top
view: one small colour chip per bypassed channel, with its name and a ⊘ glyph.
The strip hides itself entirely when nothing is bypassed, so the normal case
costs no space.

```
┌─────────────────────────────┬──────────┬──────────┐
│          TOP  (X / Y)       │  FRONT   │    3D    │
│              ,---.          │          │          │
│             ( o_o )         │  --o--   │   ╱o╲    │
│           o        o        │   (o)    │  (o_o)   │
│                             │          │          │
│ ⊘ ●Backing mix  ⊘ ●Sub 808  │          │          │
└─────────────────────────────┴──────────┴──────────┘
```

Clicking a chip selects that channel, exactly as clicking its icon would.
Clicking the ⊘ on the chip un-bypasses it, at which point it appears on the
canvases at its preserved position.

### Icons and depth

In all three views an icon's **radius encodes distance** (nearer = larger) and
its opacity encodes gain, so a glance at the top view still tells you about
height indirectly. Muted channels drop to 25% opacity; soloed ones get a glow.

## Timeline (bottom)

Ruler across the top, switchable bars:beats ↔ min:sec, with the grid drawn from
BPM and the current snap division. Channel headers on the left — colour chip,
name, gain, M/S, ⊘ (HRTF bypass), snap-override indicator. Lanes to the right.

- Clips render name + waveform; waveform detail drops out as you zoom out.
- Drag body to move; drag either edge to trim; `S` splits at playhead.
- **Shift+drag** moves the clip *and* its channel's automation (D-7).
- Snap honours the channel override, and holding `Alt` bypasses snap entirely.
- Playhead in `accent`, always drawn over everything.
- Loop region set by dragging in the ruler.
- Scroll = vertical, Shift+scroll = horizontal, Ctrl+scroll = zoom about cursor.

Implemented on `QGraphicsView` with cached waveform pixmaps per clip and
level-of-detail on zoom — at a few hundred clips a naive repaint will not hold
60 fps.

## Keyframe editor (right)

A self-contained curve editor (D-8). Its own time axis along the bottom, value
axis on the left, **scroll and zoom locked to the timeline** so the two views
always show the same time span even though they are separate widgets.

- A parameter selector at the top lists the automatable parameters of the
  selected channel, each with a visibility checkbox and a colour swatch.
  Multiple curves can be shown at once, overlaid.
- On a **bypassed** channel the `pos.*` entries are shown struck through and
  disabled, with a tooltip saying why. They are listed rather than hidden,
  because their curves still exist and come back when bypass is turned off
  (F-42) — hiding them would read as data loss. `pan` becomes available in the
  same list, and is only listed there.
- Keyframes are diamonds. Drag to move in time and value. Double-click on a
  curve inserts one; `Delete` removes the selection.
- Right-click a keyframe to set interpolation: linear / ease / hold. In `ease`
  mode bezier handles appear and can be dragged.
- Box-select multiple keyframes; drag or scale the selection as a group.
- A vertical playhead line mirrors the timeline's.
- The value axis auto-ranges per parameter, with a lock toggle.

## Transport and the ARM toggle

`● ARM` in the toolbar is automation write-arm (F-32). Off, dragging a source
icon edits the channel's static position. On, the icon turns red-ringed in all
views and dragging during playback writes keyframes at the playhead. It is a
global toggle, off at project load, and it is deliberately noisy in the UI
because silent automation writing is the single most confusing thing a DAW can
do to you.

## Keyboard

| Key | Action |
|---|---|
| `Space` | play / pause |
| `Enter` | return playhead to start |
| `L` | toggle loop |
| `S` | split selected clip at playhead |
| `Ctrl+Z` / `Ctrl+Shift+Z` | undo / redo |
| `Ctrl+D` | duplicate selection |
| `Delete` | delete selection |
| `Alt` (held) | bypass snap |
| `Shift` (held, dragging clip) | bring automation along |
| `Ctrl+S` / `Ctrl+O` / `Ctrl+N` | save / open / new |
| `Ctrl+R` | render |
| `1` `2` `3` | focus top / front / 3D view |
| `B` | toggle HRTF bypass on the selected channel |

## Accessibility and feel

- No information conveyed by colour alone: mute, solo, arm, bypass and
  missing-media all carry an icon or text as well as a colour.
- Minimum 4.5:1 contrast for text against its surface; the palette above is
  chosen to hold that.
- Every destructive action is undoable, so no confirmation dialogs except for
  discarding an unsaved project.
- The xrun counter sits in the status bar, quiet when zero, `error` when not.
