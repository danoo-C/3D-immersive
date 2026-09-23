# M9 · Phase 2 — The `.3dimtheme` file

**Status:** ✅ complete · **Plan:**
[plans/phase_2_file_format.md](plans/phase_2_file_format.md)

## Goal

A `.3dimtheme` file on disk can be turned into the `Theme` object from
[phase 1](phase_1_tokens_and_groups.md): parsed, validated, merged over the
built-in default, and reported on when it is wrong. Still nothing in the UI
selects one — this phase ends at a function and a pile of tests, including the
unhappy ones, which are the point.

## Scope

**In:** the JSON schema as specified in the *Theming* section of
[04-ui-spec.md](../04-ui-spec.md); `schema_version` and its migration hook;
key-by-key merge over the default; the failure table, every row of it; a
structured report object a caller can show in the UI; the advisory contrast
check.

**Out:** where theme files come from, and any menu →
[phase 4](phase_4_discovery_and_switching.md). The built-in default is still a
Python object until [phase 3](phase_3_builtin_as_file.md).

## Acceptance

- [x] Round-trip: a theme written out and read back yields an equal `Theme`.
- [x] **A partial theme merges.** A file containing only
      `{"schema_version": 1, "tokens": {"accent": "#FF0000"}}` yields the
      default theme with a red accent, and every other token untouched.
- [x] Every row of the failure table in `04` has a test: missing file,
      malformed JSON, unknown token key, unknown group key, invalid colour
      value, newer `schema_version`. Each returns a usable `Theme` and a report
      naming the problem — **none of them raises**.
- [x] The report is structured data, not a printed string: phase 4 has to put
      it in front of a person.
- [x] A group entry referring to a token the file does not define, but the
      default does, resolves against the default. This is the case that makes
      partial themes actually work.
- [x] The contrast check reports every token pair that falls below 4.5:1 and
      loads the theme anyway.
- [x] Loading a theme whose `schema_version` is 2 keeps what it recognises and
      says so.

## Implements

F-45, F-46, F-47, D-45, D-48. The schema, the precedence rule and the failure
table are all owned by [04-ui-spec.md](../04-ui-spec.md); `schema_version`
follows the discipline in [03-data-model.md](../03-data-model.md).

## Notes

Appended while building.

**The reader is `ui/theme_io.py` (D-77), and nothing in it raises.** A file is
parsed, dropped down to what this build understands, merged over a target
theme and handed to `Theme` already known to be well-formed. Six steps, 662
tests, eighteen mutations named before the tests were written and none
surviving.

### ⚠️ A five-line theme file could stop the application starting

Found by the battery in step 5, and it is the finding of the phase. `04`
reserves the value `"channel"` — *this channel's own colour* — and
`Theme.value()` raises on it rather than inventing a channel to resolve it
against, which is right. But `stylesheet()` asks for every group key there
is, so a theme setting `button.background` to `"channel"` produced a
perfectly well-formed `Theme` that took startup down with a `ThemeError`.

It passed everything. The JSON was valid, the value was one the
specification documents, the merge was correct and `Theme.problems()` was
empty. **A theme can be well-formed and still be one the application cannot
paint with**, and F-47's promise is about startup rather than about
construction — so the battery now builds a stylesheet from every theme it
produces, which is the assertion that would have caught it on the first run.

The fix is a rule rather than a special case: a theme may use `"channel"`
only for a key the merge target already paints per channel. Nothing does yet
— M3 draws the first clip body — so today it is accepted nowhere, and that
is the point rather than a limitation. `04` now says so where it defines the
value.

### The merge's ordering is the whole feature

Tokens are merged before any group value is checked. Done the other way
round, a partial theme that touched one group would report every group value
it did not also redefine, and the acceptance line about a group resolving
against the default would be unreachable. It is one line of ordering and it
is what D-45 actually buys.

`channels` is replaced wholesale rather than merged by index, which needed
deciding and did not need a decision row: D-75 already says the channel list
is an ordered sequence indexed by position rather than a set of keys, so
merging per index would treat those indices as the keys D-75 says they are
not — and it would make the palette's *length* unthemeable, so nobody could
ship a four-colour theme. `04`'s *Precedence* gained the sentence.

### The token vocabulary is closed, and `04` had only half of the rule

*Precedence* said a theme merges over the built-in key by key; the failure
table said an unknown token key is ignored. Together those mean a theme can
revalue a token and cannot introduce one — which is what makes a partial
theme survive a release that adds colours, and which appeared in neither
sentence. It produces two reports for one mistake, and the first message now
carries the sentence that explains the second.

### The contrast rule was implemented in the test suite

`contrast()` and `_luminance()` lived in `tests/test_theme.py`. A rule
implemented in a test suite cannot be applied to a user's file, so it moved
to `theme.py` as `contrast()`, `luminance()` and
`Theme.contrast_problems()` — beside `problems()`, because it is the same
shape: one implementation, two audiences, the built-in *held* to it and a
user's theme merely *told*. The two documented exemptions had to move with
it, or the built-in would report itself as broken on every load.

### `04`'s own example is the built-in theme

The `.3dimtheme` listing in `04` is lifted out of the document and loaded,
the test M1 phase 5 taught this project to write. `03`'s equivalent had not
loaded at all. This one does, and it comes back **equal to `BUILTIN`** — its
tokens, channels and `button` group are the built-in's key for key, so a
colour edited in the document and not in `theme.py` now fails a test. It
reports exactly two problems, `timeline` and `clip`, which are M3's groups
by `04`'s own ownership table.

### What phase 3 inherits

`load()` and `loads()` take the merge target as a parameter, so phase 3 has
something to load the built-in *as*. That is the door held open, not the
problem solved: when the built-in *is* the file there is nothing to validate
it against and nothing to merge it over, and the likely answer is that phase
3 reads its file with no target and hands the result straight to `Theme`,
which raises — because at that moment the file is code rather than input,
and phase 1's split applies unchanged.

`Severity` lives in `theme_io.py` and is expected to move to
`ui/widgets/notices.py` when phase 4 builds it. `02` already names that
module.
