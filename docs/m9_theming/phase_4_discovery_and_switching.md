# M9 · Phase 4 — Discovery and switching

**Status:** ✅ complete · **Plan:**
[plans/phase_4_discovery_and_switching.md](plans/phase_4_discovery_and_switching.md)

## Goal

Theme files in the user's theme directory are found, listed in a `View > Theme`
menu, and applied to the running application without a restart. The choice
survives the session. This is the phase where the previous three become
something a person can actually use.

## Scope

**In:** the platform-appropriate user theme directory and its creation on
first run; scanning it for `*.3dimtheme`; the `View > Theme` menu listing the
bundled theme and everything found; re-applying the stylesheet live; persisting
the selection with `QSettings`; **the notice centre** — the status-bar line,
the unread count and the list behind it, per the *Notices* section of
[04-ui-spec.md](../04-ui-spec.md) — and showing the phase 2 report through it.

**Out:** the Preferences dialog, which is M8 and will promote this menu rather
than replace it. The per-notice *actions* (relink, reveal, choose device) and
the first-run polish around them, which are M8. Hot-reload on file change — a
nice trick, no one asked for it, and it is a file watcher's worth of
complexity for a file people edit twice.

### Scope amended before the milestone started

The notice centre was added here by the gap review, from M8. It is not scope
creep: this phase's acceptance already required a broken theme to report "its
problems **in the UI**", 04 already promised that meant "not a line on stderr
nobody reads", and there was no surface anywhere in the specification for it
to appear on until M8 — six milestones later. Either this phase built one or
it could not pass. See D-65. Amended while M9 was still *not started*, which
is when [09-workflow.md](../09-workflow.md) says a phase's scope may change
freely.

## Acceptance

- [x] A `.3dimtheme` dropped into the user theme directory appears in
      `View > Theme` after the menu is next opened, without a restart.
- [x] Selecting a theme repaints the running application. Verified by a test
      that switches themes and asserts the applied stylesheet changed, and by a
      screenshot in the phase notes.
- [x] A theme changing **only** the accent visibly changes the playhead and
      focus ring and nothing else. This is the milestone's own acceptance line.
- [x] The selection persists across a restart.
- [x] A deliberately broken theme file — the one from phase 2's tests — appears
      in the menu, is selectable, reports its problems **in the UI**, and
      leaves the application running on what it could salvage.
- [x] That report reaches a person: the status bar shows the most recent
      problem, the unread count is non-zero and in `warn`, and the list behind
      it holds one entry per problem the phase 2 report contained. Nothing is
      modal, and nothing is only on stderr (F-56).
- [x] The notice count is invisible at zero, the same rule the xrun counter
      already follows.
- [x] The theme directory is created if missing, and an empty one is not an
      error.
- [x] Widgets that cache colours at construction repaint. Whatever is found
      here that does not update is the first real evidence of how the
      vocabulary needs to work for M3–M6, and belongs in the Notes.

## Implements

F-48, F-47, F-56, D-65. The `View` menu and the *Notices* surface are both
specified in [04-ui-spec.md](../04-ui-spec.md); `QSettings` here is the same
mechanism M8's session persistence will use, chosen now so M8 adopts it rather
than migrating off something else.

## Notes

Appended while building.

**Six steps, in the planned order, and every widget that existed when the
phase started now follows a theme switch without a restart.** The notice
centre came first and was consumed through one narrow interface, as the plan
said it would be; the seam it named for splitting the phase was never needed.

### D-81: the notice model has no Qt, and phase 3 predicted otherwise

Phase 3's Notes expected `Severity` to move into `ui/widgets/notices.py`.
Following that literally would have put Qt into `theme_io`'s import graph, and
through it into `theme.py`, whose headless import is the reason the whole
`.3dimtheme` format is testable without a `QApplication`. It would have been
lost quietly: every test still passes on a machine with a display. So the
model is `ui/notices.py` and only the widget is a widget, and
`test_layering.py` now asserts the theme modules are headless as a **named
set** — `theme.py` had claimed it since phase 1 and nothing checked, which is
the shape phase 3 found with D-30.

### Three things the notice surface settled that `04` left open

Now written into `04`'s *Notices* section rather than left in code:

- **The count takes the worst unread severity, not the newest.** An error
  followed by a warning is still an error waiting to be read.
- **Severity is a glyph as well as a colour** (✕ ⚠ •), because *Accessibility
  and feel* says nothing is carried by colour alone, and the one widget whose
  whole job is to be noticed would otherwise have failed that rule.
- **One notice per event, one detail line per problem.** A broken theme with
  three problems is one notice whose three lines are its problems, not three
  notices. The acceptance line's "one entry per problem" is read that way: each
  problem is its own line in the list, the count moves once per thing that
  happened, and the status line names the file rather than whichever of its
  problems arrived last. Said here because the words allow the other reading.

### What the retheme walk caught — and two things it could not

Every candidate the plan listed needed `retheme()` and has it: `Placeholder`'s
three inline sheets, the toolbar chips, both status labels, the memoised
toolbar icons, the ARM icon and the window icon. The test that asserts **no
widget anywhere keeps a built-in colour** under a theme where every token
differs found one more on its first run: notice rows removed with
`deleteLater()` stay children of the list until the event loop next turns, so
the walk found them still carrying the old palette. They are unparented now as
well as deleted.

The screenshot found the category nobody listed, and neither finding is a
colour:

- **A hidden widget still takes part in layout.** `QStatusBar` sizes itself
  from its permanent widgets, hidden ones included. The notice count took its
  compact style only when it first appeared, so until something was reported
  the bar was 36 px tall in the toolbar buttons' metrics, and every panel in
  the window moved up 12 px the first time anything was.
- **A word-wrapped label with a `Fixed` vertical policy clips.** It caps the
  row at its hint's height, and the hint is for a width of the label's own
  choosing. At the width the popup actually gave it, the broken theme's row
  needed 141 px and got 93 — and what went off the bottom were the problem
  lines, the only part of the notice that says what is wrong.

**What this says about the vocabulary for M3–M6**, which is what the last
acceptance line asked for: two kinds of widget exist, and they need different
things. A widget that bakes a colour into an inline stylesheet or a cached
rendering needs `retheme()`. A widget that reads through `theme.color()` at
paint time needs only to be repainted. And the walk is
`findChildren(QWidget)`, so **it does not reach anything that is not a
`QWidget`** — M3's timeline will be a `QGraphicsScene` of items, none of
which the walk will ever see. The view that owns the scene has to retheme its
items, or the items have to read at paint time and the view has to call
`update()`. D-82's rationale holds either way: a forgotten item keeps its old
colour visibly.

### ⚠️ Keeping the suite out of the developer's home took three attempts

Each attempt looked finished, and each was wrong in a way that could not fail
a test on the machine it was written on.

1. **Step 3** redirected `HOME`, `XDG_CONFIG_HOME` and `APPDATA` and turned on
   Qt's test mode.
2. **Step 4** found that building a `MainWindow` created a directory in the
   real config anyway — the menu listed themes, and listing called a function
   that created the directory it listed. Listing no longer creates; a real
   launch does, in `run()`. The guard moved to `conftest.py` as an autouse
   fixture, and requesting `monkeypatch` inside it moved every test's patches
   to the back of teardown, which broke a cache-clearing fixture on the first
   run. The environment is saved and restored by hand.
3. **Step 6** found the per-test redirect was an illusion: Qt caches where
   settings live the first time anything asks, so every test shared the first
   test's directory — found by a test that saw a notice raised by its
   predecessor. The redirect is session-scoped, which is the scope it actually
   had, and a second fixture empties settings and themes around every test.
   Then, reading it again: the redirect reached `QSettings` only on Linux. The
   native format is the registry on Windows and CFPreferences on macOS, and no
   environment variable reaches either — so on exactly the platforms `06`
   recommends for anything audible, the per-test `clear()` would have emptied
   the developer's real settings before every test. Settings are now forced
   into an INI file in the temporary home, and a test asserts the format and
   the path. **Not yet run on Windows or macOS**; CI's legs there are the
   first real check.

### Restoring is quiet, and falling back has to repaint

A remembered theme is restored without a notice — "Theme: VS Code Dark" on
every launch is how people learn to stop reading notices — and without being
written back, because writing back what was just read turns a read bug into a
stored one. Quiet when it works is not quiet when it does not: a restored
theme with problems still reports them. The test for D-83's fallback found it
did not fall back: it ticked the menu entry and left whatever was active on
screen, which looks right in a fresh process because the built-in is active
anyway.

### The accent line, met for the widgets that exist

There is no playhead; the timeline is M3's, and **M3 inherits that half of the
sentence along with the playhead**. For everything that exists the line is met
more precisely than it asks: under an accent-only theme the whole stylesheet
is diffed, every rule that resolved to `accent` changes, and no other byte
does. As first written, the assertion naming the focus ring could not fail —
every changed line contains the new accent by construction, and the focus
check was or'ed with exactly that. It names the `:focus` selector now.

### The screenshot is described here, not committed

Taken offscreen with `QWidget.grab()` and looked at, in three states: the
built-in, an accent-only theme, and the deliberately broken one. The first two
differ only in the active tab's underline and in the notice announcing the
switch — the focus ring is accent too, and does not show in a still. The third
shows *Theme: Broken — 3 problems* on the status line, an amber `⚠ 2` beside
the xrun counter, and a list holding the broken theme's notice — each problem
on its own line — above the accent theme's. [doc-system.md](../doc-system.md)
keeps image files out of `docs/`, and the part of the screenshot that can be
re-run is `test_the_accent_reaches_actual_pixels`, which finds the new colour
in a real rasterised grab.

### What the mutation sweep found

Seventeen mutations named in the plan and three added while running them.
Five of the seventeen survived a first run and four of those were real — the
first point below covers two — and one of the three additions survived too.
All five real ones are caught now.

- **D-82's order was asserted only through its consequences**, and moving
  `use()` after the sheet has none today — `stylesheet()` is handed the theme,
  and nothing between the cache clears and `use()` reads a colour. It would
  have gone on surviving until the first time something did. The order is now
  recorded call by call, and the same test is the only thing that notices the
  window icon's cache going uncleared: nothing looks at the window icon's
  pixels.
- **The rescan was tested through `repopulate()` called by hand**, so
  disconnecting it from `aboutToShow` — F-48's whole mechanism — left every
  test green. The test opens the menu now.
- **A directory made at import is invisible to the suite by construction.**
  Test modules are imported during collection, before any fixture has
  redirected anything, so it would land in the real home of whoever ran the
  tests. A fresh interpreter with an empty home is the only place it shows.
- **Step 4's own bug had no test pinning its fix.** Reverting the one argument
  that stops listing the themes from creating their directory survived
  everything. Not on the plan's list — added while running it, because the
  bug was.

The plan's fifth survivor weakens the accent-only test to "some rule changed",
and nothing else catches it — correctly, as phase 3 found with its own
mutation aimed at a test: a second assertion on the same fact would be a
second home for it. What it was meant to ask is whether that test has teeth,
so that was asked directly: handed a theme that also changes the border, it
fails.
