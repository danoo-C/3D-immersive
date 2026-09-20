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
│  MEDIA POOL   │ ┌ Top / Front ┬──── 3D ───┐     │  KEYFRAME EDITOR  │
│               │ ├─────────────┴───────────┴───┐ │                   │
│  ▾ drums      │ │     TOP        │    FRONT   │ │  ╭─╮              │
│    ▪ kick.wav │ │    (X / Y)     │   (X / Z)  │ │ _╯ ╰──╮           │
│    ▪ hat.wav  │ │                │            │ │       ╰───        │
│  ▾ pads       │ │     (o_o)      │    ──o──   │ │                   │
│    ▪ warm.wav │ │    o     o     │     (o)    │ │  ├──┼──┼──┼──┤    │
│               │ └────────────────┴────────────┘ │                   │
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

### The workspace is tabbed

Two tabs, not three side-by-side views (D-49):

| Tab | Holds | Why together |
|---|---|---|
| **Top / Front** | the two editable ortho views, split vertically | Placing a source is one gesture across both — X/Y here, then height there. Separating them would make every position edit a tab switch |
| **3D** | the read-only isometric view | It is for *reading* the scene, never for editing, so it does not compete for the pixels the editable views need |

Keys `1` and `2` focus the top and front views, selecting the first tab if it
is not already showing; `3` selects the 3D tab. The tab selection persists with
the rest of the layout.

Three views side by side each got about a third of the workspace, which at
1500 px is too narrow to drag anything precisely in — and a third of that space
was going to a view that cannot be dragged in at all.

## Colour palette

Surfaces are VS Code's dark greys; the accent stays purple (D-44). The
surfaces are monotonic — `bg-0` is the deepest and each step is lighter — and
widgets must rely on that ordering rather than on the literal values, because
a theme may replace them ([theming](#theming)).

| Token | Hex | Use |
|---|---|---|
| `bg-0` | `#181818` | application background, deepest |
| `bg-1` | `#1F1F1F` | panel surfaces |
| `bg-2` | `#252526` | headers, raised elements |
| `bg-3` | `#2D2D2D` | hover, selected row |
| `border` | `#3C3C3C` | 1px separators, splitter handles |
| `text-hi` | `#CCCCCC` | primary text |
| `text-lo` | `#9D9D9D` | labels, secondary text |
| `text-dim` | `#6E6E6E` | disabled |
| `accent` | `#A855F7` | purple **fills and strokes**: playhead, focus ring, active toggle |
| `accent-dim` | `#7E3FF2` | pressed state |
| `accent-glow` | `#C77DFF` | hover, keyframe highlight, and **any purple that carries text** |
| `warn` | `#F59E0B` | clipping, missing media |
| `error` | `#F88A8A` | xruns, load failures |

⚠️ `accent` is 4.17:1 against `bg-1` — enough for a UI component, not enough
for text. That is why it is specified as a fill and stroke colour and why
`accent-glow` (6.13:1) exists as the text-safe purple. On the previous
purple-black surfaces `accent` cleared 4.5:1; against lighter greys it does
not, and the same shift is why `error` moved from `#EF4444` (4.38:1, failing)
to VS Code's own error-text red. `tests/test_theme.py` computes these ratios,
so the rule cannot rot quietly.

### Channel palette

Assigned round-robin on channel creation, user-overridable. All chosen to stay
legible on `bg-1` and distinguishable from each other and from `accent`.

`#A855F7` `#22D3EE` `#F59E0B` `#34D399` `#F472B6` `#60A5FA` `#FB923C` `#A3E635`

A channel's colour is used for: its header chip, its clips, its icon in all
three spatial views, and its curves in the keyframe editor. That colour thread
is the main navigational aid in the app — it is the one visual rule to never
break.

## Icons

Icons ship as **SVG**, one file per icon in `assets/icons/`, drawn on a 16 px
grid. Each one paints its ink with the literal token `currentColor`, which is
substituted for a palette colour when the icon is loaded (D-50). Qt's SVG
renderer does not resolve `currentColor` itself, so this is a textual
substitution before rendering, not a CSS cascade.

That indirection is what makes the set themeable: one asset per icon, recoloured
at load, rather than a folder of PNGs per theme. It also means M9 retints every
icon in the application without shipping a second copy of any of them.

| | |
|---|---|
| Grid | 16 px, rendered at 16 and 32 for hidpi |
| Ink | `currentColor`, substituted at load |
| Normal state | `text-hi` |
| Disabled state | `text-dim`, supplied explicitly |
| Shipped today | `transport_start` `play` `pause` `stop` `loop` `undo` `redo` |

Disabled icons are rendered from the palette rather than left to Qt, whose
default is to wash the normal pixmap out until it reads as a rendering fault
rather than a state.

## Menus

Standard desktop behaviour, stated because one half of it is easy to lose:

- A menu opens on **click**.
- With a menu already open, moving along the menu bar **walks between menus**.
  Qt normally provides this, but the open popup grabs the mouse and on some
  compositors — WSLg among them — the moves never reach the menu bar, so the
  application implements it explicitly (D-51).
- Hovering does **not** open the first menu. A menu bar that springs open as
  the pointer crosses it on the way to the toolbar is not helpful.
- An action that is not yet implemented is disabled and says why in its
  tooltip. A menu of enabled items that do nothing is worse than a grey one.

## Craft

The difference between "dark and minimal" and "cheap" is mostly a handful of
rules applied consistently. These are not suggestions; a panel that breaks one
looks broken next to the panels that do not.

| Rule | Because |
|---|---|
| Every panel has a **header bar** — small caps, `text-lo` on `bg-2`, 1 px bottom border — not a caption floating in the middle | A titled panel reads as a region of an application; a centred label reads as an empty box |
| **No ASCII glyphs as UI.** `|<` and `[]` are placeholders, never shipped | They are the single loudest signal that something is unfinished |
| One **font stack**, resolved per platform, never a single named family | Naming one family gets an unchosen fallback on the two platforms that lack it |
| Spacing is a multiple of 2 px, padding of 4 | Arbitrary offsets read as misalignment even when nobody can say why |
| **Tooltips carry the shortcut**, in the form `Action  (Key)` | The keyboard table below is the specification; the tooltip is how anyone finds out |
| Disabled states are drawn deliberately, from the palette | See the icons note above |
| Accent is used sparingly — selection, playhead, focus, the active tab | An accent on everything is an accent on nothing |

## Theming

The palette above is the **default** theme, not the only one. Every colour the
application draws is named, and a `.3dimtheme` file can replace any of those
names (F-44, F-45). The built-in default is itself such a file, loaded through
the same path as a user's (D-47) — a format that cannot express the default
theme is already broken, and this is how we find that out in a test rather
than in a bug report.

Built here rather than at M8: see M9 in [06-roadmap.md](06-roadmap.md).

### Two layers

A theme has `tokens` and `groups`, and the split is the whole design (D-46).

**Tokens** are named colours — the thirteen in the palette table above, plus
the channel list. Change eight of them and the whole application is coherently
retinted, because everything else refers to them by name.

**Groups** are per-widget roles: what a button's background is, what a clip's
selected border is, what colour a keyframe diamond takes. A group's value is
either a **token name** or a literal `#RRGGBB`. Referring to a token by name
is strongly preferred; a literal is the escape hatch for the one case a theme
author wants to break the family.

Without groups, a theme could not say "this one thing is different". Without
tokens, a theme would be a list of several hundred colours that nobody would
edit by hand. Both layers earn their place.

### The file

```json
{
  "schema_version": 1,
  "name": "VS Code Dark",
  "author": "3d immersive",
  "tokens": {
    "surface.window": "#181818",
    "surface.panel": "#1F1F1F",
    "surface.raised": "#252526",
    "surface.hover": "#2D2D2D",
    "border": "#3C3C3C",
    "text.primary": "#CCCCCC",
    "text.secondary": "#9D9D9D",
    "text.disabled": "#6E6E6E",
    "accent": "#A855F7",
    "accent.pressed": "#7E3FF2",
    "accent.text": "#C77DFF",
    "warn": "#F59E0B",
    "error": "#F88A8A"
  },
  "channels": ["#A855F7", "#22D3EE", "#F59E0B", "#34D399",
               "#F472B6", "#60A5FA", "#FB923C", "#A3E635"],
  "groups": {
    "button": {
      "background": "surface.hover",
      "text": "text.primary",
      "border": "border",
      "hover.border": "accent.text",
      "pressed.background": "accent.pressed"
    },
    "timeline": {
      "playhead": "accent",
      "grid": "border",
      "loop.region": "accent.pressed"
    },
    "clip": {
      "body": "channel",
      "selected.border": "accent",
      "fade.handle": "text.secondary"
    }
  }
}
```

`"channel"` is the one reserved value: it means *this channel's own colour*,
resolved per channel at paint time. It is what keeps the colour thread from
the Channel palette section intact under any theme.

`schema_version` carries the same migration discipline as `.3dim` — see
[03-data-model.md](03-data-model.md).

### Precedence

A loaded theme is **merged over** the built-in default, key by key (D-45):

```
built-in default  ->  the theme file's tokens  ->  the theme file's groups
```

So a two-line theme that sets only `accent` is valid, and — the property that
matters — it is *still* valid after a later milestone adds tokens for widgets
that did not exist when it was written. A theme that replaced the palette
wholesale would break on every release that added a colour.

### When a theme is wrong

Never fatally (F-47, D-48). A theme file is cosmetic, and a typo in one must
not stand between someone and their project.

| Problem | What happens |
|---|---|
| File missing or unreadable | Default theme, reported |
| Malformed JSON | Default theme, reported with the parse error |
| Unknown token or group key | Ignored, reported — it is probably a newer theme |
| Invalid colour value | That key falls back to the default, reported |
| `schema_version` newer than we know | Load what we recognise, report the rest |

"Reported" means visible in the UI, not a line on stderr nobody reads.

### Contrast is checked, not enforced

A theme is validated against the 4.5:1 rule in *Accessibility and feel* below
and any failure is reported to its author — but it still loads. Enforcing the
rule would mean refusing somebody's own theme on their own machine, which is
not a call this application gets to make. The **default** theme is a different
matter: it is held to the rule by `tests/test_theme.py`.

### The vocabulary grows

There is no complete list of groups today, and writing one now would be
fiction: the widgets for clips, waveforms, keyframes and the spatial views do
not exist until M3-M6. **Each milestone adds its own groups to this section as
it builds them.** That is a standing obligation of every milestone from here
on, not a task belonging to M9.

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
- Minimum 4.5:1 contrast for text against its surface, on every surface from
  `bg-0` to `bg-3`, asserted by `tests/test_theme.py`. Two documented
  exemptions, both standard: `text-dim`, which is disabled text, and `accent`,
  which is not a text colour — see the palette note above.
- Every destructive action is undoable, so no confirmation dialogs except for
  discarding an unsaved project.
- The xrun counter sits in the status bar, quiet when zero, `error` when not.
