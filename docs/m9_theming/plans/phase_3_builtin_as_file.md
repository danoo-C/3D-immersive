# Plan — M9 · Phase 3 — The built-in theme becomes a file

**Written:** 2026-09-23 · **Status:** in progress

## Approach

The thirteen tokens, eight channels and eleven groups move out of `theme.py`
into `src/immersive/assets/themes/vscode_dark.3dimtheme`, generated from the
object that holds them today so the values cannot drift in the move. What
reads them is a **strict** read: the bundled theme is code, it ships in the
wheel, and a malformed one is a bug that must not reach anybody — so it
raises where a user's theme reports.

The migration is deliberately in two steps rather than one. **Step 1 puts the
file in the tree and proves it is the default while the constants are still
there.** Step 3 deletes them. A single step that wrote the file and deleted
the constants in one commit would have nothing to compare against at the
moment the comparison is worth anything.

What makes the whole phase cheap to verify is something phase 1 already left
behind: `tests/fixtures/stylesheet_before_m9.qss`, a byte-for-byte golden of
the rendered stylesheet. Its stated expiry is "the first time a milestone
legitimately changes a colour", and this phase changes none. So the proof
that no pixel moved is a fixture that already exists and already passes, and
the phase's second acceptance line costs nothing to meet.

## Two things the phase doc does not settle

Both become rows in the decision log, taking the next free numbers, written
in step 1 with the high-water mark in [doc-system.md](../../doc-system.md)
§3. Not cited by number here, for the reason phase 1's plan gave: a reference
to an identifier that does not exist yet is the one thing §7's check cannot
tell from a mistake.

### ⚠️ There is no fallback palette, and there cannot be one

The phase doc's Scope says "the fallback if the bundled resource is somehow
unreadable" is in. Read as *a fallback theme*, that is not implementable
alongside the phase's own first acceptance line: a palette to fall back to is
thirteen colours in `theme.py`, and the acceptance is that
`grep -riE '#[0-9a-f]{6}' src/immersive/ui/theme.py` returns nothing. One of
the two has to give.

The acceptance wins, and the fallback becomes a *behaviour* rather than a
palette: **an unreadable or malformed bundled theme refuses to start, with a
message naming the resource.** Three reasons, and the third is the one that
settles it:

- It is a **packaging** failure, not a runtime condition. The file is inside
  the wheel. If it is missing, the installation is broken, and every other
  thing the application is about to do is also broken.
- A fallback palette would be a second definition of the default theme, kept
  in a second place, used by nobody in any run that ever works. The first
  time the two disagreed, the disagreement would be invisible.
- **`theme.py` already behaves this way.** `_template()` reads `app.qss`
  through `importlib.resources` with no fallback at all; a missing stylesheet
  takes the application down today. A bundled theme that fell back where the
  bundled stylesheet does not would be two rules for one category of thing.

What prevents it is not a fallback, it is `tests/test_package.py` plus CI
installing the wheel rather than the source tree — which is D-27's whole
stated benefit and is already collected.

### ⚠️ `BUILTIN` becomes a function, and there is a cycle in the way

Today `theme_io` imports `theme`. One direction, clean. The moment the
built-in theme is read from a file, something has to read it, and both
candidates create a problem:

| Where the reader goes | What breaks |
|---|---|
| `theme.py` | it needs `SCHEMA_VERSION` and the document mapping, which live in `theme_io` — so `theme` imports `theme_io` imports `theme` |
| `theme_io.py` | `theme.active()` needs a default and `theme.py` cannot import `theme_io` at module level, for the same cycle |

The third option — move `SCHEMA_VERSION` and the format's document mapping
into `theme.py` — is the one that looks cleanest and is worst. It splits the
`.3dimtheme` format across two modules, which is precisely what D-77 argued
against four weeks ago when it put the format in one place.

**So: `builtin()` lives in `theme_io.py`, and `theme.py` reaches it through a
deferred import inside one private helper.** A function-level absolute import
is still greppable, which is what D-28 cares about, and it is one line with a
comment on it rather than a format split in half.

It is also a *function* rather than a constant, `@cache`d, read on first use:

- `theme.py` already has exactly this pattern in `_template()`, for exactly
  this kind of thing — "the stylesheet template, read once per process".
- A module-level `BUILTIN = _read()` does file I/O at import and can **raise
  at import**, which turns a packaging fault into an ImportError inside
  somebody's traceback instead of a message at startup that names the file.
- It is D-76's instinct one layer out: read when asked, do not capture.

The cost is 64 references, 55 of them in tests. That is mechanical and it is
the whole cost.

## Not a decision: what "through the phase 2 loader" can mean now

The phase doc's third acceptance line says the bundled theme "loads through
the phase 2 loader, not a shortcut past it". It was written before phase 2
existed, when the loader was assumed to have one mode. It has two, and they
are two because the milestone's central split requires it: **a theme that is
code raises, and a theme that is input reports.**

`loads()` cannot read the built-in. It filters every key against a merge
target's vocabulary, and the built-in *is* the vocabulary — there is nothing
to merge it over and nothing to validate it against except itself. Handing it
`loads()` would mean handing it an empty target, against which every key in
the file is unknown.

So the line is met as follows, and this is an interpretation rather than a
change, stated here rather than assumed: **`theme_io` remains the only thing
in the application that turns a `.3dimtheme` into a `Theme`.** The bundled
theme goes through the same module, the same `schema_version` handling and
the same `Theme` constructor, by a strict entry point beside the lenient one.
A test asserts the startup path calls `theme_io`, which is what "not a
shortcut past it" is protecting.

Worth noticing rather than quietly satisfying, because the acceptance's
*intent* — do not build the default by some private route that the format
never has to express — is exactly right, and is met.

### What validates a file that nothing can be validated against

Nothing extra needs building, which is the pleasant surprise in this phase.
Three checks already exist and together they are sufficient:

1. `Theme.problems()` catches everything internal: a group naming a token the
   file does not define, a malformed hex, an empty channel list, an unnamed
   theme. It raises, because the built-in is code.
2. **`stylesheet()` catches a vocabulary that is short.** `Template.substitute`
   raises on a placeholder with no value, and `app.qss` names every group key
   the application draws. A bundled theme missing a group key cannot render
   the sheet, and the existing test notices.
3. `Theme.contrast_problems()` catches a default that breaks the 4.5:1 rule,
   and phase 2 moved it into the package precisely so it could run on
   something other than a Python object.

## Steps

1. **The decisions, and the file exists without being read.** Two decision
   rows, the high-water mark. `src/immersive/assets/themes/` with its
   `__init__.py`, and `vscode_dark.3dimtheme` generated by
   `theme_io.dumps(BUILTIN)` rather than typed. `test_package.py` asserts it
   is reachable as a resource, beside the stylesheet and the icons.
   *Test:* the bundled file loads through `theme_io.loads` over the existing
   `BUILTIN` and yields a theme **equal to `BUILTIN`** — the file is proven
   to be the default while the thing it is being compared against still
   exists, which is the one moment that comparison is worth making.

2. **The strict read, and `builtin()`.** A strict entry point in `theme_io`
   that raises rather than reports, and `builtin()` — `@cache`d, reading the
   bundled resource through `importlib.resources`.
   *Test:* it returns a theme equal to the constants; a self-inconsistent
   document raises naming the group and the key; a document with a malformed
   colour raises; a missing resource raises naming the resource rather than
   surfacing a bare `FileNotFoundError`. The strict reader takes text, so all
   of that is testable without a broken file in the tree.

3. **The flip, and the constants are deleted.** `theme.py` loses its palette;
   `_active` resolves through the deferred import; the 64 references move.
   *Test:* `stylesheet()` still equals `tests/fixtures/stylesheet_before_m9.qss`
   byte for byte — phase 1's golden, unexpired, and the whole proof that this
   phase changed no pixels; no hex literal survives in `theme.py`, asserted
   by reading the module rather than by grep; the contrast suite now runs
   against a theme that came off disk; `use()` still takes effect, because
   D-76 is easy to re-break while moving an active-theme default around.

4. **D-30, the wheel, and `04`.** A test asserting the theme module does no
   `__file__` path-walking. A wheel assertion. `04`'s palette table names the
   file as its implementation, the way it named `theme.py` before.
   *Test:* `importlib.resources` is the only route to the file; the built
   wheel contains it.

Four steps. The phase is smaller than phase 2 because phase 2 built the
machine; this one points it at one file and deletes what it replaces.

## Files

```
docs/01-requirements.md                          amended — two decision rows
docs/doc-system.md                               amended — the D high-water mark
docs/04-ui-spec.md                               amended — the palette table names
                                                   the file as its implementation
docs/m9_theming/phase_3_builtin_as_file.md       amended — Notes
src/immersive/assets/themes/__init__.py          new
src/immersive/assets/themes/vscode_dark.3dimtheme  new — generated, not typed
src/immersive/ui/theme.py                        amended — the palette leaves,
                                                   the lazy default arrives
src/immersive/ui/theme_io.py                     amended — strict read, builtin()
tests/test_theme.py                              amended — 19 references
tests/test_theme_io.py                           amended — 36 references
tests/test_icons.py                              amended — 3 references
tests/test_package.py                            amended — the theme ships
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| The golden stylesheet regenerated rather than asserted | the phase moves a pixel and says it did not, and the one cheap proof is spent | it is a mutation below; the fixture is not touched in any step, and a step that needs to touch it is a step that has changed a colour |
| `@cache` on `builtin()` outliving a test that swaps the resource | a test passes against a theme read three tests ago — the icon-cache trap phase 1 found, one module over | a fixture calls `cache_clear()`, and `builtin()`'s docstring says why, the same way `icons.icon()`'s does |
| A module-level import sneaking back in | an import cycle that only fails on a fresh interpreter in the wrong order | the deferred import is tested by importing `immersive.ui.theme` first in a subprocess, and `theme_io` first in another |
| `_active` captured at import while it is being made lazy | D-76 broken again, invisibly, one phase before the phase that needs it | a test that swaps the active theme and asserts a call site follows, which already exists and must keep passing |
| The theme file not reaching the wheel | the application starts unstyled for everyone who installed rather than checked out — D-27's exact failure | asserted in `test_package.py` beside the stylesheet and the icons, and CI installs the wheel |
| The generated file hand-edited afterwards | the file and `dumps()` disagree, and the next regeneration produces a spurious diff | the file is generated once, in step 1, and every later change to it is a change to the theme rather than to its formatting |

**Mutations named in advance**, to run against the finished suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| the golden stylesheet regenerated instead of asserted | the phase changes pixels silently |
| `builtin()` returning a theme built in Python rather than read | the file ships and nothing uses it, which is the phase not done |
| the strict read reporting instead of raising | a malformed default ships and the application paints something nobody chose |
| the strict read skipping `Theme` construction | nothing validates the built-in at all |
| a token deleted from the bundled file | `stylesheet()` should refuse to render; if it does not, check 2 above is not real |
| a group key deleted from the bundled file | the same, one level down |
| `schema_version` removed from the bundled file | the strict read should refuse it |
| `builtin()` not cached | re-read per call. Likely **equivalent** — nothing observable depends on it. Pin it with a test that counts reads, or record it as equivalent and say why |
| `builtin()` cached but never cleared between tests | the phase 1 icon trap, reproduced |
| `active()` defaulting to something other than the built-in | the application starts on a theme nobody chose |
| `_active` captured at import | `use()` silently does nothing, and phase 4 cannot switch |
| `importlib.resources` swapped for `__file__` path-walking | works from a source tree, breaks under PyInstaller at M8 (D-30) |
| the theme file excluded from the wheel | works checked out, unstyled installed |
| the file read as bytes without an encoding | works on Linux CI, breaks on a Windows machine with a non-UTF-8 default |
| the contrast suite left pointed at a Python theme | the shipped default stops being held to 4.5:1 while appearing to be |

The genuine unknown is **whether anything outside `theme.py` and the tests
holds a colour that came from the constants**. `icons.py` reads tints through
the accessor and `main_window.py` and `placeholder.py` were ported in phase 1
step 4, so the answer should be no — but "should be" is what phase 1's
`@cache` discovery was made of, and the module that memoises a rendered
`QIcon` against its arguments is the same module here.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| A second bundled theme, or light mode | nobody asked for one; M9 makes it possible, not present |
| Discovery, the `View > Theme` menu, switching without a restart | [phase 4](../phase_4_discovery_and_switching.md) |
| The notice centre, and the report reaching a person | phase 4 (D-65) |
| `icons.icon.cache_clear()` on a theme switch | phase 4 — this phase changes the *default*, which never switches |
| PyInstaller verification | M8 owns it; D-30 is honoured here so that it is not a discovery there |
| Groups for widgets M2–M6 will draw | those milestones, per `04`'s ownership table |

## Outcome

Filled in at the end.
