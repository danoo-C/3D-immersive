# M9 · Phase 3 — The built-in theme becomes a file

**Status:** ✅ complete · **Plan:**
[plans/phase_3_builtin_as_file.md](plans/phase_3_builtin_as_file.md)

## Goal

The default palette stops living in Python and becomes
`assets/themes/vscode_dark.3dimtheme`, loaded at startup through exactly the
same path as a user's theme. After this phase `theme.py` contains no colours at
all — it contains the code that reads them.

This is the phase that tests the format rather than the loader: if the schema
from [phase 2](phase_2_file_format.md) cannot express the application's own
default theme, it cannot express anyone else's either, and better to find that
here than in a bug report.

## Scope

**In:** the theme file itself, under `src/immersive/assets/themes/`; loading it
with `importlib.resources` per D-30, never `__file__`; the fallback if the
bundled resource is somehow unreadable; updating the palette table in `04` to
name the file as the source of truth.

**Out:** shipping a second theme — see the milestone README. PyInstaller
packaging is verified here but owned by M8.

## Acceptance

- [x] `grep -riE '#[0-9a-f]{6}' src/immersive/ui/theme.py` returns nothing.
- [x] The application starts and looks **identical** to the phase 1 screenshot.
      Same proof as phase 1, same reason.
- [x] The bundled theme loads through the phase 2 loader, not a shortcut past
      it — asserted by a test that patches the loader and sees it called.
- [x] The file is accessed via `importlib.resources`, and a test asserts no
      `__file__` path-walking in the theme module (D-30 exists because that
      breaks under PyInstaller, which is exactly where it is hardest to debug).
- [x] The wheel contains the theme file. `pyproject.toml` already carries an
      `artifacts` entry for the gitignored SOFA sets; themes are committed, so
      confirm they are packaged rather than assuming it.
- [x] Contrast tests now run against the *file*, so the shipped default cannot
      drift out of the 4.5:1 rule.

## Implements

D-47, D-30. The palette table in [04-ui-spec.md](../04-ui-spec.md) remains the
specification; this phase makes the theme file its implementation, the way
`theme.py` was before.

## Notes

Appended while building.

**The palette is `assets/themes/vscode_dark.3dimtheme` and `theme.py` holds
no colour at all.** Four steps, and the proof that no pixel moved was already
in the tree: phase 1's golden stylesheet fixture is byte-compared and still
matches, its stated expiry has not arrived, and this phase never touched it.

### The migration was two steps on purpose

Step 1 put the file in the tree and proved it equal to `BUILTIN` **while
`BUILTIN` still existed**. After step 3 there is nothing on the other side of
that equals sign, so the assertion that says "this file is the default" has
exactly one moment in which it can be made. A single commit doing both would
have had nothing to compare.

### ⚠️ Nothing can validate the built-in, and nothing needed to

The bootstrap that phase 2 handed over looked like the hard part: the reader
validates a file against a merge target's vocabulary, and the built-in *is*
the vocabulary. It turned out three checks already existed and together they
are sufficient — which is why this phase built no validator.

`Theme.problems()` catches everything internal. **`stylesheet()` catches a
vocabulary that is short**, because `app.qss` names every group key and
`Template.substitute` raises on a placeholder with no value; that one is now
asserted rather than assumed, and the mutation sweep confirms deleting a
group key from the bundled file is caught. And `contrast_problems()` holds
the shipped default to 4.5:1 off disk, which is what phase 2 moved it into
the package for.

So `strict()` sits beside `loads()` rather than inside it, and the reason is
structural: `loads()` filters every key against a target's vocabulary, and
handing it a theme that has no target means handing it one against which
every key is unknown. Code raises, input reports — the milestone's split, one
level up from where phase 1 first drew it.

### D-79: the fallback is a behaviour, not a palette

The Scope line asked for "the fallback if the bundled resource is somehow
unreadable", and read as a fallback *theme* it cannot coexist with this
phase's own first acceptance line — a palette to fall back to is thirteen
colours in `theme.py`. The acceptance won. `_template()` already reads
`app.qss` with no fallback at all, so falling back here would have been two
rules for one category of thing.

### D-80: a cycle, and one deferred import

`theme_io` imports `theme`. Reading the default from a file needs a reader,
and both obvious homes close the loop. Moving the format's constants into
`theme.py` would have split `.3dimtheme` across two modules, which is what
D-77 put it in one place to avoid. So `builtin()` lives in `theme_io` and
`theme.py` reaches it through a deferred import in one private helper, tested
in both import orders in a fresh interpreter each — a cycle fails in only one
of the two.

### What the mutation sweep found

Fifteen named, **four survived the first run, three were real.**

- **D-30 was asserted for one module and not the other.** `theme.py` had the
  test since phase 1; `theme_io.py` started reading a resource in this phase
  and had nothing, so the rule held by accident. Swapping `importlib` for
  `__file__` path-walking there survived the entire suite.
- **The bundled theme's encoding was explicit and untested.** Latent rather
  than live, since the file is ASCII — and latent is exactly the class M1
  phase 5 named, a cross-platform behaviour asserted on one platform.
- **D-80's second half had no test.** Nothing observed whether the default
  was read at import or on demand, because the answer is the same theme
  either way. What differs is that a broken installation raises at import
  instead of at startup.

The fourth is not a gap and is recorded as mis-specified. It weakens a
*test* rather than the code, and nothing else catches the difference — which
is the correct state of affairs. Mutating a test only ever asks whether some
other test overlaps it.

### What phase 4 inherits

Two themes that can be compared, a loader with both of its modes, and a
report with severities waiting for a surface. The things phase 4 has to
remember are already written down: `icons.icon()` is memoised and must be
`cache_clear()`ed on a switch, `builtin()` is memoised too, and `Severity`
is expected to move to `ui/widgets/notices.py`, which `02` already names.
