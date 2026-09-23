# M9 · Phase 2 — The `.3dimtheme` file

**Status:** not started · **Plan:** not written yet —
`plans/phase_2_file_format.md`

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

- [ ] Round-trip: a theme written out and read back yields an equal `Theme`.
- [ ] **A partial theme merges.** A file containing only
      `{"schema_version": 1, "tokens": {"accent": "#FF0000"}}` yields the
      default theme with a red accent, and every other token untouched.
- [ ] Every row of the failure table in `04` has a test: missing file,
      malformed JSON, unknown token key, unknown group key, invalid colour
      value, newer `schema_version`. Each returns a usable `Theme` and a report
      naming the problem — **none of them raises**.
- [ ] The report is structured data, not a printed string: phase 4 has to put
      it in front of a person.
- [ ] A group entry referring to a token the file does not define, but the
      default does, resolves against the default. This is the case that makes
      partial themes actually work.
- [ ] The contrast check reports every token pair that falls below 4.5:1 and
      loads the theme anyway.
- [ ] Loading a theme whose `schema_version` is 2 keeps what it recognises and
      says so.

## Implements

F-45, F-46, F-47, D-45, D-48. The schema, the precedence rule and the failure
table are all owned by [04-ui-spec.md](../04-ui-spec.md); `schema_version`
follows the discipline in [03-data-model.md](../03-data-model.md).

## Notes

Appended while building.
