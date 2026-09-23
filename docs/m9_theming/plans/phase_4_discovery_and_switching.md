# Plan — M9 · Phase 4 — Discovery and switching

**Written:** 2026-09-23 · **Status:** in progress

## Approach

Three things that do not obviously belong together: a menu that lists theme
files, a repaint that does not restart the application, and a notice centre.
They are one phase because the phase's own acceptance needs all three — a
broken theme has to be *selectable*, has to *report*, and has to leave the
application running — and because the notice centre was moved here from M8
before the milestone started, for exactly that reason (D-65).

**This is six steps, which is [09](../../09-workflow.md)'s stated limit, and
the seam is named up front.** If it grows, steps 1 and 2 are the notice centre
and they split off cleanly: they have their own acceptance lines, they touch
no theme code, and every later step consumes them through one narrow
interface. The rest of the phase is discovery, switching and persistence.

The interesting engineering is not the menu. It is that **widgets bake colours
into inline stylesheets at construction** — `Placeholder` does it three times,
`MainWindow._chip()` once per chip, the status bar twice — and `icons.icon()`
memoises a rendered `QIcon` against its arguments. D-76 made the *accessors*
read at call time; nothing made the *widgets* re-read. Phase 1's Outcome
flagged the icon cache and this is the phase that pays for it.

## Three things the phase doc does not settle

Rows in the decision log, written in step 1 with the high-water mark. Not
cited by number here, for the reason every plan in this milestone has given.

### ⚠️ Where the notice vocabulary lives, and why phase 3 predicted wrong

Phase 3's Notes say `Severity` "is expected to move to
`ui/widgets/notices.py`, which `02` already names". Following that literally
breaks something worth more than the tidiness:

> `theme_io` carries `Severity` on every problem it reports. If `Severity`
> lives in a Qt widget module, **`theme_io` imports Qt** — and with it
> `theme.py`, because that is where `theme_io`'s own import goes.

`theme.py` says in its first docstring that it has no Qt import at module
level "so the palette and the stylesheet are testable headless", and every
test in `test_theme_io.py` runs without a `QApplication` today. That property
is not decoration: it is why the whole format is testable at all.

So the notice **model** is a Qt-free `ui/notices.py` — `Severity`, a `Notice`
record, and the session's log — and only the **widget** is
`ui/widgets/notices.py`, which is what `02` describes. `theme_io` imports the
model. Two modules share a name, which is a real cost and the smaller one;
the import lines disambiguate them and the alternative is Qt in the palette.

It also answers a question this phase did not have to ask but M2 will: F-3's
missing media needs the same vocabulary, and having it in `theme_io` would
have been absurd.

### The remembered selection is a path, not a name

`QSettings` has to hold *which theme*, and the two candidates fail
differently. A **name** is what the user sees and is not unique — two files
can both call themselves "Ocean", and the one that wins is whichever the
directory scan reached first. A **path** is unambiguous and survives a rename
of the theme inside the file.

So: the absolute path for a user theme, and a sentinel for the built-in,
which has no path. A stored path that no longer resolves falls back to the
built-in **and posts a notice** — somebody deleted their theme and the
application should say it noticed, not silently look different.

### Live restyling is an explicit `retheme()` protocol

Three ways to repaint, and the third is the only one that survives M3–M6:

| | |
|---|---|
| rebuild the window | loses every bit of session state the moment there is any, and there will be by M3 |
| a Qt signal each widget connects to | every widget has to remember to connect, and the one that forgets fails silently — which is the exact failure mode F-44 exists to prevent |
| **walk the widget tree and call `retheme()` where it exists** | a widget that forgets is *visible*, because it keeps the old colour while everything around it changes |

The walk is `window.findChildren(QWidget)` plus the window itself, calling
`retheme()` on anything that has one. Capability rather than registration:
nothing has to be told about a new widget.

And the order matters, which is the part that is easy to get wrong:
`theme.use()` first, then `icons.icon.cache_clear()` and
`app_icon.cache_clear()`, then the application stylesheet, then the walk. A
widget that re-reads a colour before `use()` has landed gets the old one.

## ⚠️ One acceptance line cannot be met as written, and it is not this phase's fault

> *A theme changing **only** the accent visibly changes the playhead and focus
> ring and nothing else.*

**There is no playhead.** The timeline is M3's, `04`'s ownership table says
so, and the built-in theme has no `timeline` group — phase 2's test of `04`'s
own worked example asserts that `timeline` and `clip` are the two groups
nothing has built yet.

The line is the milestone's, from the roadmap: *"a user theme file that
changes only the accent visibly works"*. The phase doc sharpened it to name
two widgets, and one of them arrives two milestones later. So it is met for
the widgets that exist, and met precisely rather than loosely:

- **Every** stylesheet rule that resolves to `accent` changes, and **no other
  byte of the sheet does.** Asserted by diffing the rendered sheet under both
  themes — which is a stronger statement than "the focus ring changed" and is
  exactly what "and nothing else" means.
- The focus ring is one of those rules, named in the test so the assertion
  keeps its connection to what the line was asking about.
- The screenshot covers "visibly", and M3 inherits the playhead half of the
  sentence along with the playhead.

Said here rather than quietly narrowed. The acceptance is not being edited.

## Steps

1. **The decisions, and the notice model.** `ui/notices.py`, Qt-free:
   `Severity` (moved from `theme_io`), a frozen `Notice` with severity, text,
   detail and a monotonic sequence number, and the session log that holds
   them with an unread count. `02` gains the module. Three decision rows, the
   high-water mark.
   *Test:* the log keeps insertion order and newest-first reading; unread
   counts and clears; `theme_io`'s report converts to notices with its
   severities intact; **`ui/notices.py` imports no Qt**, asserted the way
   `test_layering.py` asserts `core/` does not.

2. **The notice surface.** `ui/widgets/notices.py`: the status-bar line
   carrying the most recent notice, the count beside the xrun counter —
   invisible at zero, `warn` or `error` coloured by the worst unread — and
   the list behind it, newest first, each row with severity, time and
   message. Wired into `MainWindow`'s status bar. Nothing modal.
   *Test:* zero notices renders no count; a `warn` colours it `warn`; a
   `warn` then an `error` colours it `error`; the line shows the newest; the
   list holds one row per notice; opening it clears unread. Per-notice
   *actions* are M8 and are not here.

3. **Discovery.** `theme_io.discover(directory)` — Qt-free, sorted,
   `*.3dimtheme` only, a missing directory is an empty result rather than an
   error. `ui/theme_menu.py`'s `user_theme_directory()` resolves the
   platform-appropriate location through `QStandardPaths` and creates it on
   first use.
   *Test:* files are found and sorted; a directory that does not exist yields
   nothing and raises nothing; an empty one is not an error; a file with the
   wrong extension is ignored; the directory is created once and creating it
   twice is fine.

4. **The menu, and the repaint.** `View > Theme`, repopulated on
   `aboutToShow` so a file dropped in appears without a restart, listing the
   built-in first and then what was found, checkable, exclusive.
   `MainWindow.apply_theme()` in the order above, and `retheme()` on
   `Placeholder`, the toolbar chips, the status labels and the window icon.
   *Test:* a theme selected changes `QApplication.styleSheet()`; a file added
   after the window was built appears on the next open; a `Placeholder`'s
   header colour follows a switch; the toolbar icons are re-rendered rather
   than served from the cache; **no widget keeps a colour from the old
   theme**, asserted by walking the tree and comparing.

5. **Persistence.** `QSettings` under the organisation and application names
   `app.py` already sets; the path for a user theme and a sentinel for the
   built-in; restored at startup; an unresolvable path falls back and posts a
   notice.
   *Test:* a selection survives a new `MainWindow`; the sentinel restores the
   built-in; a stored path whose file has gone restores the built-in and
   leaves exactly one notice. **The tests must not write the developer's real
   settings** — a fixture redirects `QSettings` to a temporary location and
   is the first thing this step writes.

6. **End to end, and the accent.** The deliberately broken theme from phase
   2's tests, placed in the theme directory: it appears, it is selectable, it
   reports through the notice centre, and the application goes on running on
   what it could salvage. Then the accent-only assertion above, and the
   screenshot.
   *Test:* the milestone's acceptance line, as one test that does the whole
   journey; the stylesheet diff under an accent-only theme; a screenshot
   grabbed offscreen — `QT_QPA_PLATFORM=offscreen` is already set in
   `conftest.py`, so `widget.grab()` produces a real image without a display.

## Files

```
docs/01-requirements.md                    amended — three decision rows
docs/doc-system.md                         amended — the D high-water mark
docs/02-architecture.md                    amended — ui/notices.py, theme_menu.py
docs/04-ui-spec.md                         possibly amended — whatever the
                                             notice surface settles that the
                                             Notices section left open
docs/m9_theming/phase_4_*.md               amended — Notes
src/immersive/ui/notices.py                new — the model, Qt-free
src/immersive/ui/widgets/notices.py        new — the surface
src/immersive/ui/theme_menu.py             new — directory, menu, persistence
src/immersive/ui/theme_io.py               amended — discover(), Severity moves out
src/immersive/ui/main_window.py            amended — the menu, apply_theme, retheme
src/immersive/ui/widgets/placeholder.py    amended — retheme()
src/immersive/ui/icons.py                  amended — cache_clear on switch
tests/test_notices.py                      new
tests/test_theme_menu.py                   new
tests/test_theme_io.py                     amended — Severity's new home
tests/test_main_window.py                  amended — the View menu grew
tests/test_layering.py                     amended — ui/notices.py stays Qt-free
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| Tests writing the developer's real `QSettings` | a test run that changes the machine it ran on, and a persistence test that passes because of yesterday's run | step 5 writes the fixture before the feature; `QSettings.setPath` to `tmp_path`, autouse |
| A widget that bakes a colour and has no `retheme()` | it keeps the old theme's grey and nothing fails | the tree walk plus a test that compares every widget's stylesheet before and after a switch, rather than checking the ones we remembered |
| The icon cache serving the old theme | the toolbar stays the old colour after a switch — phase 1 predicted this exact failure | `cache_clear()` in `apply_theme`, ordered before the walk, with a test that asserts a re-render rather than a call |
| `theme_io` acquiring Qt through the notice import | the palette stops being testable headless, quietly | the model module is Qt-free and a layering test says so |
| Repopulating the menu on `aboutToShow` rescanning on every open | a directory scan on a UI thread, every time somebody opens View | it is one `iterdir` of a directory holding a handful of files; measured rather than assumed if it ever matters |
| The screenshot committed as a binary | `docs/` grows a file nobody diffs | decide in step 6: generate it, look at it, and commit it only if the Notes are worse without it |

**Mutations named in advance**, run against the finished suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| `theme.use()` called after the stylesheet is rebuilt | the new sheet is built from the old theme, and one switch lags by one |
| `icons.icon.cache_clear()` not called | the toolbar keeps the old theme's ink |
| `app_icon.cache_clear()` not called | the window icon does, which is the one nobody looks at |
| the `retheme()` walk visiting only direct children | nested placeholders keep the old colour |
| the walk calling `retheme()` before `theme.use()` | every widget re-reads the colour it already had |
| the notice count visible at zero | `04`'s rule, and the xrun counter's |
| the count coloured by the newest notice rather than the worst unread | an error goes quiet behind a later warning |
| the notice log keeping only the newest | "notices persist for the session" is the line it breaks |
| unread cleared on *arrival* rather than on opening the list | the count is always zero |
| discovery matching any extension | a `.txt` in the theme directory becomes a theme |
| discovery raising on a missing directory | first run, before anything has created it |
| the theme directory created at import rather than on use | a test run makes a directory in the developer's config |
| the remembered value stored as the theme's name | two themes called "Ocean", and the wrong one restored |
| an unresolvable stored path falling back silently | the theme somebody chose is gone and nothing says so |
| a broken theme file refused rather than listed | the phase's own acceptance, inverted |
| the menu populated once at build rather than on `aboutToShow` | a dropped-in file needs a restart, which is F-48 |
| the accent-only test asserting *some* rule changed rather than *only* accent rules | "and nothing else" stops being checked |

The genuine unknown is **how much the retheme walk actually catches**. The
phase doc's last acceptance line says whatever does not update here is "the
first real evidence of how the vocabulary needs to work for M3–M6", which is
an invitation to find something. The candidates are known — `Placeholder`'s
three inline sheets, four toolbar chips, two status labels, the icon cache,
the window icon — and the interesting result would be a category nobody
listed.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The Preferences dialog | M8, which promotes this menu rather than replacing it |
| Per-notice actions — *Relink…*, *Reveal*, *Choose device…* | M8 (D-65). This phase builds the surface; M8 hangs actions off it |
| Hot-reload when a theme file changes on disk | nobody asked for it, and it is a file watcher's worth of complexity for a file people edit twice |
| A second *bundled* theme | not a consequence of the system; a decision nobody has made |
| The xrun counter becoming live | M3, which is the first milestone with a stream to count |
| Missing-media notices | M2, which is the next caller of this surface (F-3) |
| Groups for widgets M2–M6 draw | those milestones, per `04`'s ownership table |

## Outcome

Filled in at the end.
