# 04 — UI Specification

## Layout

Dark, minimal, purple accent. Every boundary below is a draggable splitter; the
layout itself is fixed (D-15).

```
┌──────────────────────────────────────────────────────────────────────┐
│  File   Edit   View   Transport   Render   Help                      │
├──────────────────────────────────────────────────────────────────────┤
│  ⏮ ▶ ⏹ ↻ │ 1.1.000 │ 120.0 BPM  4/4 │  Snap 1/16 ▾ │  ⟲ ⟳  │  ● ARM │
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

`1.1.000` is the **playhead readout** (F-52): bars.beats.ticks, or
minutes:seconds when the ruler is switched, drag-scrubbable and typeable like
every other numeric field. The ruler shows where the playhead is; only this
gives a value you can read off, note down or type back in.

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
surfaces are monotonic — `surface.window`, `surface.panel`, `surface.raised`,
`surface.hover`, deepest to lightest — and widgets must rely on that ordering
rather than on the literal values, because a theme may replace them
([theming](#theming)). The names are the ones a `.3dimtheme` uses (D-74);
there is deliberately only one set.

**This table is the specification; its implementation is a file.** The values
below ship as `src/immersive/assets/themes/vscode_dark.3dimtheme`, read at
startup through the same module that reads anybody else's theme (D-47). They
were thirteen constants in `theme.py` until M9 phase 3, and that module now
holds no colour at all — a test asserts it. A value edited here and not there
fails a test too: the built-in theme is loaded and compared against this
table on every run.

| Token | Hex | Use |
|---|---|---|
| `surface.window` | `#181818` | application background, deepest |
| `surface.panel` | `#1F1F1F` | panel surfaces |
| `surface.raised` | `#252526` | headers, raised elements |
| `surface.hover` | `#2D2D2D` | hover, selected row |
| `border` | `#3C3C3C` | 1px separators, splitter handles |
| `text.primary` | `#CCCCCC` | primary text |
| `text.secondary` | `#9D9D9D` | labels, secondary text |
| `text.disabled` | `#6E6E6E` | disabled |
| `accent` | `#A855F7` | purple **fills and strokes**: playhead, focus ring, active toggle |
| `accent.pressed` | `#7E3FF2` | pressed state |
| `accent.text` | `#C77DFF` | hover, keyframe highlight, and **any purple that carries text** |
| `warn` | `#F59E0B` | clipping, missing media |
| `error` | `#F88A8A` | xruns, load failures |

⚠️ `accent` is 4.17:1 against `surface.panel` — enough for a UI component, not enough
for text. That is why it is specified as a fill and stroke colour and why
`accent.text` (6.13:1) exists as the text-safe purple. On the previous
purple-black surfaces `accent` cleared 4.5:1; against lighter greys it does
not, and the same shift is why `error` moved from `#EF4444` (4.38:1, failing)
to VS Code's own error-text red. `tests/test_theme.py` computes these ratios,
so the rule cannot rot quietly.

### Channel palette

Assigned round-robin on channel creation, user-overridable. All chosen to stay
legible on `surface.panel` and distinguishable from each other and from `accent`.

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
| Normal state | `text.primary` |
| Disabled state | `text.disabled`, supplied explicitly |
| Shipped today | `transport_start` `play` `pause` `stop` `loop` `undo` `redo` `arm` `app` |

Two of those are not toolbar glyphs. `arm` is the dot this document draws as
`● ARM`, an icon rather than a character so that the Craft rule against ASCII
glyphs as UI holds for it too — and so a theme retints it with everything
else. `app` is the application's own mark, used for the window and taskbar
icon; it is the one icon drawn in `accent` rather than `text.primary`, because it
has to carry identity rather than sit quietly in a panel, and it renders from
its own size ladder up to 256 px since alt-tab and dock previews ask for sizes
no toolbar ever does.

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
  tooltip — not "not yet", but which milestone brings it. A menu of enabled
  items that do nothing is worse than a grey one; a grey one with no
  explanation is only slightly better. `tests/test_main_window.py` walks every
  action in the menus *and* the toolbar and asserts it, because for a while
  the rule was tested only on the toolbar, where it already held, while all
  nineteen disabled menu actions were bare.
- Qt suppresses tooltips inside a `QMenu` unless asked (`setToolTipsVisible`).
  Worth stating because the failure mode is invisible: the explanations exist
  on the actions, reach nobody, and the code looks finished.

## Craft

The difference between "dark and minimal" and "cheap" is mostly a handful of
rules applied consistently. These are not suggestions; a panel that breaks one
looks broken next to the panels that do not.

| Rule | Because |
|---|---|
| Every panel has a **header bar** — small caps, `text.secondary` on `surface.raised`, 1 px bottom border — not a caption floating in the middle | A titled panel reads as a region of an application; a centred label reads as an empty box |
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
the Channel palette section intact under any theme. A theme file may use it
**only for a key the built-in theme already paints per channel** — `clip.body`
and its like, once M3 draws them. Anywhere else it is ignored and reported:
there is no channel for it to resolve against, so a five-line theme file would
otherwise be able to stop the application painting, which is the one thing
F-47 says a theme must never do.

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

**The vocabulary is closed**, which is the other half of that rule and is easy
to miss. A theme file can give a new value to a token the built-in already
defines; it cannot introduce one. A `tokens` entry the built-in does not know
is an unknown key, and the table below says unknown keys are ignored and
reported. That is what makes merging safe in both directions — a name that
means nothing today cannot quietly come to mean something else in the release
that adds it.

`tokens` and `groups` merge key by key; **`channels` is replaced wholesale.**
A file that gives a channel palette gives all of it. The list is an ordered
sequence indexed by position rather than a set of keys (D-75), so merging it
per index would treat those indices as keys — and it would make the palette's
*length* unthemeable, so a four-colour theme could not exist.

It has one consequence worth stating plainly, because it produces **two
reports for one mistake**. A file that defines `"my.purple"` and then writes
`"playhead": "my.purple"` in a group has its token dropped as unknown; the
group value then names a token that does not exist, so that key falls back to
the default and is reported a second time. Both messages are true and each
names what it saw. The first one says the vocabulary is fixed, which is the
sentence that explains the second.

### When a theme is wrong

Never fatally (F-47, D-48). A theme file is cosmetic, and a typo in one must
not stand between someone and their project.

| Problem | What happens |
|---|---|
| File missing or unreadable | Default theme, reported |
| Malformed JSON | Default theme, reported with the parse error |
| Valid JSON, but not an object | Default theme, reported |
| Unknown token or group key | Ignored, reported — it is probably a newer theme |
| Invalid colour value | That key falls back to the default, reported |
| `schema_version` absent, or not a whole number | Default theme, reported. The version is read before anything else, so there is nothing to read it as |
| `schema_version` newer than we know | Load what we recognise, report the rest |

"Reported" means visible in the UI, not a line on stderr nobody reads.

**None of this applies to the built-in theme**, which is code rather than
input. A group of it naming a token that does not exist is a bug that must not
ship, so it raises where it is constructed and a test catches it on the way in.
The same split runs through the next section, where contrast is enforced on
the default and merely reported for a user's: one rule, two audiences. A typo
in somebody's own theme file must not stand between them and their project; a
typo in ours must not reach them at all.

### Contrast is checked, not enforced

A theme is validated against the 4.5:1 rule in *Accessibility and feel* below
and any failure is reported to its author — but it still loads. Enforcing the
rule would mean refusing somebody's own theme on their own machine, which is
not a call this application gets to make. The **default** theme is a different
matter: it is held to the rule by `tests/test_theme.py`.

### Choosing a theme

Themes live in a `themes` folder inside the application's config directory —
`~/.config/3d immersive/3d immersive/themes` on Linux, where Qt nests the
organisation name and the application name and the two happen to be the same,
and the platform's equivalent elsewhere, resolved by Qt rather than assembled
per platform. A real launch creates it, so there is somewhere to drop a file;
nothing else does, and an empty or missing one simply means there are no user
themes.

`View > Theme` lists the bundled theme first, by its name, then every
`.3dimtheme` in that folder, by file name. It is **rescanned each time the
menu opens**, so a file dropped in appears without a restart (F-48); there is
no file watcher, and a theme edited on disk is re-read when it is next chosen.
With none installed, a disabled entry says so and its tooltip names the
folder. Every file found is listed and selectable, including a broken one —
choosing it is how its author finds out what is wrong with it.

Choosing a theme repaints the running application and is remembered by
**path** (D-83). At the next launch it is restored **quietly**: replaying a
previous session's choice is not news, and a notice on every launch is how
people learn to stop reading them. Quiet when it works is not quiet when it
does not — a restored theme with problems reports them, and one whose file has
gone falls back to the built-in and says so.

### The vocabulary grows

There is no complete list of groups today, and writing one now would be
fiction: the widgets for clips, waveforms, keyframes and the spatial views do
not exist until M3-M6. **Each milestone adds its own groups to this section as
it builds them.** That is a standing obligation of every milestone from here
on, not a task belonging to M9.

To make that obligation something you can check rather than remember, here is
who owns what. M9 is built *third*, before all of them:

| Groups | Owner |
|---|---|
| window, panel, menu, toolbar, button, **tab**, splitter, scrollbar, status bar, tooltip, **focus** | M9 — the widgets that exist when the system is built. Tab and focus were missing from this row until M9 phase 1 went looking: the tab bar exists because of D-49 and the focus ring is required by *Accessibility and feel*, and the stylesheet has styled both since M0 |
| notice line, notice count, notice list | M9 — it builds them (D-65) |
| tree view, header, filter field, waveform thumbnail | M2 — built as `tree`, `header`, `filter` and the painted `waveform`. The filter is styled by its object name |
| ruler, grid, playhead, loop region, clip body, clip selected border, fade handle, channel header, meter | M3 — the ruler, grid and playhead built at phase 1 as the painted `ruler` and `timeline` groups, the second named and shaped by the worked example under *The file*; the channel header at phase 2 as `channel`, styled by object name, with the line between lanes as `timeline.separator`; the clip body at phase 3 as the painted `clip` group, the first with keys painted per channel; the clip's selected border and the rubber
band at phase 4 as `clip.selected.border` and `timeline.band`, and a
selected header as `channel.selected.background` and
`channel.selected.marker` |
| head glyph, distance ring, source icon, motion trail, bypass chip | M5 |
| curve, keyframe diamond, bezier handle, value axis | M6 |
| input field | M3 — built at phase 2 as `input`, for the numeric field a channel's gain is the first to use. It was listed under M8 for whichever milestone drew one first, and that turned out to be this one |
| dialog, progress bar, spin box, check box, slider, combo box | M8 — the first milestone with dialogs and a preferences form |

**Painted groups.** Some widgets draw with a painter rather than a
stylesheet — the waveform is the first, and clips, the spatial views and the
curves will follow. Their groups are named in `theme.PAINTED` (D-92), read by
`group_color()` when the widget paints, and held by a test to having every
key read by something, just as the stylesheet's groups are held to its
placeholders. The waveform's, built at M2:

| `waveform` key | Default | For |
|---|---|---|
| `background` | `surface.panel` | behind the lanes |
| `centre` | `border` | the zero line — what silence looks like |
| `fill` | `text.secondary` | the envelope, one lane per channel |
| `missing` | `warn` | a sample whose file has gone, which also says so in text |

The timeline's, built at M3. The lanes and the playhead draw from
`timeline`, whose `grid` and `playhead` values the worked example under *The
file* already gave; the ruler draws from its own group. The three grid
colours rely on the surfaces being monotonic, deepest first, and not on
their values:

| `timeline` key | Default | For |
|---|---|---|
| `background` | `surface.panel` | behind the lanes |
| `grid` | `border` | bar lines — the strongest |
| `grid.beat` | `surface.hover` | beat lines |
| `grid.division` | `surface.raised` | the snap division — the faintest, and only while snapping is on |
| `playhead` | `accent` | the playhead, over everything, in the lanes and across the ruler |
| `separator` | `border` | the line under each lane |
| `drop` | `accent` | the dashed outline of where a drop from the pool will land |
| `band` | `accent` | the rubber band's outline, over a faint fill of the same |

The clips', built at M3 as the worked example under *The file* named them.
`body` and `waveform` are the reserved `channel` value — the first keys any
widget paints per channel — so a theme may paint every clip one colour, and
the built-in paints each in its channel's:

| `clip` key | Default | For |
|---|---|---|
| `body` | `channel` | the clip, translucent over its lane |
| `waveform` | `channel` | the envelope, solid over the body |
| `text` | `text.primary` | the clip's name |
| `missing` | `text.disabled` | the body of a clip whose sample has gone, which also says so in text |
| `selected.border` | `accent` | a 2 px border inside a selected clip — a shape as well as a colour |

| `ruler` key | Default | For |
|---|---|---|
| `background` | `surface.raised` | behind the ticks and labels |
| `tick` | `text.disabled` | tick marks |
| `text` | `text.secondary` | labels |

The QSS today styles none of the input widgets in that last row, which is
correct — nothing renders one yet. It is listed so that the milestone which
first does knows the groups are its to add, rather than discovering a
`QLineEdit` drawn in the toolkit's default light grey on a dark panel and
reaching for a literal hex to fix it. That reach is the failure mode this
whole milestone exists to prevent.

## Media pool (left, top)

Folder tree of imported audio. Per row: name, duration, a one-line waveform
thumbnail. Filter box at the top.

- Double-click auditions the sample (non-spatial, straight to the output).
- Drag a row onto a timeline channel to create a clip.
- Drag onto empty timeline space to create a new channel holding it.

A drop lands on the lane under the pointer, at the sample under it snapped
to the grid and to every clip's edges on any channel (F-13, F-17), by that
channel's own snap setting (F-18), or exactly where it was dropped while
`Alt` is held. Several rows dropped together go end to end from there, in
the order the pool lists them, and below the last lane one new channel holds
them all. A dashed outline shows where it will land before the release. A
drop over existing clips trims them to make room, removes those it covers,
and splits one it lands inside (D-95); with Shift held, a drop that would
overlap is refused, and the pointer says so before the release. Each drop is
one Undo, the new channel included.
- Missing files show in `warn` with a relink action.

The folders mirror those beneath what was imported: the deepest folder every
sample shares is the root, so importing one folder shows its subfolders and
not the path to it. A missing row says so in words — `⚠` before its name — as
well as in `warn`.

A dragged row carries **`application/x-3dimmersive-media`**: a JSON list of
the dragged samples' media ids, in the order they appear. This is the
contract the timeline accepts at M3.

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

```
┌─────────────┬──────────────────────────────┐
│ Add channel │ ruler — follows the lanes →  │
├─────────────┼──────────────────────────────┤
│ ■ Name  snap│                              │
│ 0.0 dB M S ⊘│ lanes — scroll both ways     │
├─────────────┤                              │
│ headers     │                              │
│ follow the  │                              │
│ lanes ↕     │                              │
└─────────────┴──────────────────────────────┘
```

The headers never scroll sideways and the ruler never scrolls up and down;
each follows the lanes on the other axis, so a header is always level with
its own lane. The corner above the headers holds *Add channel*, in reach
however far the lanes are scrolled.

- **Gain** runs from −60 dB to +12 dB, dragged or typed like every numeric
  field. Below −60 is what mute is for, and a fader that reaches −∞ spends
  its most-used range in its last few pixels.
- **M, S and ⊘** are letters or a symbol as well as a colour when on. A
  channel silenced by another's solo says *silenced* beside its name; a muted
  one does not, because its M already says why it is quiet.
- **The snap indicator** reads `snap` while the channel follows the project,
  and the division — `1/8`, `1/4T`, `off` — while it overrides it.
- **The name** is renamed by double-clicking it, and ends in an ellipsis
  rather than running into the controls beside it.
- **The chip** is the channel's own colour, from the project. Clicking it
  offers the theme's channel palette. Dragging a header up or down reorders
  the channels, and a right-click offers Rename and Remove.
- **Clicking a header** selects its channel, with the modifiers a clip
  takes (*Selection*). A selected header wears a bar down its left edge as
  well as a lighter background, and the bar's room is always there, so
  selecting a header does not shift what is in it.

The grid thins as the view zooms out rather than crowding: no two lines are
drawn closer than a few pixels, the snap division goes first, then beats, and
bars are thinned to every second, fourth or eighth bar but never removed. The
division is drawn only while snapping is on, because it is there to show
where a drag will land.

- Clips render name + waveform; waveform detail drops out as you zoom out.
  A clip is its channel's colour, translucent over the lane, with its part
  of its sample drawn solid over that — a trimmed clip shows its own frames,
  not its sample's start. Narrower than a few pixels it is its body alone,
  and its name ends in an ellipsis until even that would not fit. A clip
  whose sample is missing is grey and says *⚠ missing* in its name strip.
- Drag body to move; drag either edge to trim; `S` splits at playhead.
- **Shift+drag** moves the clip *and* its channel's automation (D-7).
- Snap honours the channel override, and holding `Alt` bypasses snap entirely.
- Playhead in `accent`, always drawn over everything.
- Loop region set by dragging in the ruler.
- Scroll = vertical, Shift+scroll = horizontal, Ctrl+scroll = zoom about cursor.
  A trackpad's or a tilt wheel's sideways movement scrolls along time with no
  key held, and a **middle-button drag pans both ways**, the lanes following
  the hand — the gesture pro tools give a mouse with only an up-and-down
  wheel, which otherwise needs Shift for every move through time.

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

### The value axis, with several curves overlaid

One axis cannot carry `pos.x` in metres, `gain` in dB and `pan` in −1…+1 at
once, so with more than one curve shown **each is normalised to its own
range** and the axis labels the **focused** curve — the one whose keyframes
respond to the mouse, picked in the parameter selector (D-66).

That keeps both halves of what the overlay is actually for. Across curves you
are comparing *shape and timing* — does the gain dip while it passes behind
you — which normalisation preserves exactly. For the one you are editing, the
numbers on the axis are its real units.

A lock toggle freezes the ranges so a curve does not re-scale under the cursor
while you drag a keyframe past its previous extreme. With a single curve shown
this is all invisible: it auto-ranges to that parameter and the axis is its
own.

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
| `Esc` | stop |
| `Enter` | return playhead to start |
| `L` | toggle loop |
| `S` | split selected clip at playhead |
| `Ctrl+Z` / `Ctrl+Shift+Z` | undo / redo |
| `Ctrl+X` / `Ctrl+C` / `Ctrl+V` | cut / copy / paste clips |
| `Ctrl+D` | duplicate selection |
| `Ctrl+A` | select all clips on the focused channel |
| `Delete` | delete selection |
| `Alt` (held) | bypass snap |
| `Shift` (held, dragging clip) | bring automation along |
| `Ctrl+S` / `Ctrl+O` / `Ctrl+N` | save / open / new |
| `Ctrl+R` | render |
| `1` `2` `3` | focus top / front / 3D view |
| `B` | toggle HRTF bypass on the selected channels |

This table is the specification, and where a toolkit default disagrees with it
the table wins: `QKeySequence.StandardKey.Redo` resolves to `Ctrl+Y` on Linux
and Windows, so redo is written out rather than taken from it (D-68). Qt maps
`Ctrl+` onto Command on macOS by itself, so one spelling is correct on all
three platforms.

## The open project

There is always exactly one, held by the window and owned by a document that
knows its file and its history (D-85). A new window holds an empty, untitled
one.

- The **title** names it — its file's stem, or *Untitled* — and marks unsaved
  changes the platform's own way, through Qt's `[*]`: an asterisk on Windows
  and Linux, a dot in the close button on macOS.
- **New, Open and Quit over unsaved changes ask once**: *Save*, *Discard* or
  *Cancel*. Nothing is asked when there is nothing unsaved. *Save* goes ahead
  only if the save worked — a Save As dialog that was cancelled, or a write
  that failed, must not be followed by throwing away the project somebody
  just asked to keep. This is the one confirmation named under
  *Accessibility and feel*.
- A name typed into Save As without a suffix gets `.3dim`, or the Open dialog's
  own filter hides the file the next time anyone looks for it.
- **Success is quiet.** Opening and saving post nothing; the title's mark
  clearing is the feedback. A project that will not open is an `error` notice
  carrying the reasons, and the project that was open stays open, history and
  unsaved changes included. One that opens with media missing is **one**
  `warn` notice whose detail lines name each missing file (F-3).

## Notices — where "reported" goes

Several requirements promise that something is *reported*: missing media
(F-3), a theme that is missing, malformed or contains bad colours (F-47), a
decode that failed, a device that would not open (F-56). All of them mean the
same thing — visible in the UI, not a line on stderr nobody reads — and none
of them had anywhere to appear. This section is that place (D-65).

It is **one surface, not a dialog per caller.** A modal for a cosmetic theme
typo is the behaviour F-47 exists to prevent; a `print()` is the behaviour it
exists to prevent in the other direction.

### The shape

```
┌──────────────────────────────────────────────────────────────────────┐
│ Backing.wav could not be found                        ⚠ 3   xruns 0  │
└──────────────────────────────────────────────────────────────────────┘
                                                        ▲
                             click to open the list of everything reported
```

- The **status bar** carries the most recent notice as one line, and a count
  of unread ones beside the xrun counter. The count is coloured by the
  **worst** unread notice rather than the newest — an error followed by a
  warning is still an error waiting to be read — and is invisible at zero, the
  same rule the xrun counter already follows. Its severity is a glyph as well
  as a colour (✕ ⚠ •), because nothing here is carried by colour alone.
- **One notice per thing that happened.** A theme file with three problems is
  one notice whose detail lines are its three problems, not three notices: the
  count moves once, and the status line names the file rather than whichever
  problem was found last.
- Clicking the count opens the **notice list**: a popover of everything
  reported this session, newest first, each with its severity, its time, its
  message, its detail lines and, where there is one, an action — *Relink…* for
  missing media, *Reveal* for a theme file, *Choose device…* for a stream that
  would not open. Opening the list marks everything in it read, which is what
  makes the count go away.
- Notices persist for the session and are cleared explicitly. A message you
  can only read in the second it appears has not been reported to anybody.

### Severity

| | Means | Example |
|---|---|---|
| `error` | something the user asked for did not happen | project failed to load, device would not open |
| `warn` | it happened, with a caveat they need to know | media missing and greyed, theme key ignored, clipping |
| info | it happened | render finished, theme applied |

Nothing here is modal. The one confirmation in the application stays the one
named under *Accessibility and feel* below: discarding an unsaved project.

### Built at M9, not M8

The general error surfaces were an M8 bullet, and M9 — built third — needs
this to satisfy its own acceptance line about a broken theme reporting itself.
F-3 needs it at M2. Building it where the first requirement for it lands costs
a small widget; leaving it at M8 means six milestones each invent their own
message box. See D-65.

## Master meter

A stereo peak meter sits in the status bar, left of the notice count: two
narrow bars, peak-hold for 1.5 s, and a clip indicator that latches in `warn`
until clicked (F-54).

It is small and always visible, because the thing it answers is not a question
anyone thinks to ask until the render is already clipped: thirty-two sources
summing in the frequency domain, each scaled by a distance attenuation that
*moves while it plays*, do not have a predictable sum. A channel's fader
position tells you nothing about what reaches the bus.

Per-channel meters are deliberately not provided (D-55) — that is a mixing
console, which [00-overview.md](00-overview.md) puts out of scope, and solo
plus the parameters pane answers the same question at the rate this
application needs it answered.

## Selection

One kind of thing at a time, plural within that kind (D-57).

| | |
|---|---|
| Kinds | clips · keyframes · channels · media files |
| Switching kind | clears the previous one — selecting a clip deselects every keyframe |
| Plural | click, `Shift+click` for a range, `Ctrl+click` to toggle one, `Ctrl+Shift+click` to add a range |
| Rubber band | drag on empty lane space in the timeline, or on empty space in the keyframe editor; with `Ctrl` or `Shift` it adds |
| Across channels | yes, for clips and keyframes |
| `Ctrl+A` | every clip on the focused channel; again for every clip in the project |
| Clearing | click empty space, or `Esc` when the transport is stopped |
| Where | a clip in the lanes, a channel by its header, a sample by its row in the pool |

Mixing kinds was considered and rejected: `Delete` with a clip *and* a
keyframe selected has no answer a modifier can rescue, and every edit verb in
the application belongs to exactly one kind.

**The range** runs from the *anchor* — the thing last clicked or
Ctrl-clicked — to the thing clicked, and replaces the selection; with
`Ctrl` it is added instead. For channels that is every header between the
two. For clips it is the rule file managers teach, carried across the two
dimensions a timeline has: every clip that overlaps the stretch of time from
the earlier of the two to the later, on every lane from the anchor's to the
clicked one's.

**A press on a selected clip waits for the release.** A press on an
unselected clip selects it at once. A press on one already selected leaves
the selection alone, so that a drag from any selected clip can move them all,
and only a release that never moved selects that clip alone. Every file
manager and every DAW behaves this way; a click that changed its meaning when
dragging arrived would be learnt twice.

**The focused channel** that `Ctrl+A` reads is the one last clicked, by its
header or by one of its clips. With none, the first `Ctrl+A` already selects
every clip in the project. A line edit keeps `Ctrl+A` and `Esc` for itself:
with a channel's name being edited they select its text and cancel the
rename, and the selection is untouched.

**`Esc`** is *Stop*, and clears the selection when the transport is already
stopped. Until the transport exists (M3 phase 9) it always is: Stop is
disabled, a disabled action's shortcut does not fire, and `Esc` reaches the
window, which clears the selection. Phase 9's Stop keeps that rule.

**`B`** toggles HRTF bypass on every selected channel as one edit: if any is
off they all go on, and if all are on they all go off, so a mixed selection
comes out of one press agreeing. With no channel selected it is disabled, and
its tooltip says to select one.

**What marks a selection** is a shape as well as a colour (*Accessibility
and feel*): a 2 px border inside a clip, a bar down a header's left edge, the
highlighted row in the pool. The pool's tree keeps a selection of its own
because Qt insists on one; it is kept in step with the document's both ways,
and never decides anything by itself.

The parameters pane follows the selection. With several things of one kind
selected it shows the fields they have in common, and a field whose value
differs across the selection reads `—` until it is set, at which point it is
set on all of them.

## Accessibility and feel

- No information conveyed by colour alone: mute, solo, arm, bypass and
  missing-media all carry an icon or text as well as a colour.
- Minimum 4.5:1 contrast for text against its surface, on every surface from
  `surface.window` to `surface.hover`, asserted by `tests/test_theme.py`. Two documented
  exemptions, both standard: `text.disabled`, which is disabled text, and `accent`,
  which is not a text colour — see the palette note above.
- Every destructive action is undoable, so no confirmation dialogs except for
  discarding an unsaved project — *Save*, *Discard* or *Cancel*, as *The open
  project* above describes.
- The xrun counter sits in the status bar, quiet when zero, `error` when not.
  Beside it, left to right: the master meter, the notice count, the version.
- **Keyboard focus is always visible**, as a 1 px `accent` ring. Left to the
  toolkit it is neither purple nor consistent across platforms, and "no
  information by colour alone" cuts both ways — a focus indicator nobody can
  see fails keyboard users first. The tab bar is the one exception, because
  its selected tab already carries an accent rule and a second indicator on
  one widget is noise.
