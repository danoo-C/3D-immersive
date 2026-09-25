# The documentation system

How this project's documentation is organised, numbered and changed.

This file is **meta** — deliberately unnumbered, because it is not part of the
product specification. It describes the containers; the numbered documents
describe the thing being built. Its companion is
[09-workflow.md](09-workflow.md), and the boundary between them is worth
stating once: **this file governs how documents are written and organised;
`09` governs how work is sequenced.** Anything about milestones, phases or
plans belongs there.

---

## 1. The map

| Where | What it is | Changes |
|---|---|---|
| `README.md` (repo root) | The original hand-written spec, kept verbatim as the record of intent, plus a pointer to `docs/` | Almost never |
| `docs/README.md` | The index and reading order | Whenever a document is added |
| `docs/doc-system.md` | This file | Rarely |
| `docs/00`–`09` | **The canon.** The specification of the product and its process | Deliberately, with a reason |
| `docs/<milestone>/` | Working documents: phases and plans, per [09](09-workflow.md) | Constantly, while that milestone is live |
| `.github/workflows/README.md` | Colocated notes for a thing that is not the product | With that thing |
| `LICENSE`, `THIRD-PARTY-NOTICES.md` | Legal facts, not documentation. Kept at the root because that is where tools and people look for them | When a dependency or a bundled dataset changes |
| Docstrings | How a specific module works | With the code |

### The canon

| # | Owns |
|---|---|
| `00-overview` | What the app is, the stack, scope boundaries, the "later, maybe" list |
| `01-requirements` | **All** F-, N- and D- identifiers. The decision log. |
| `02-architecture` | Layering, repo layout, threading, imports and packaging, the port seam |
| `03-data-model` | Coordinates, time, entities, the `.3dim` format |
| `04-ui-spec` | Layout, palette, panels, interactions, keyboard |
| `05-audio-engine` | The HRTF pipeline, the per-block hot path, realtime safety |
| `06-roadmap` | Milestones, their order, the risk register |
| `07-qa-archive` | Closed questions and the answers given. Append-only. |
| `08-environment` | venv, `launch.py`, the installer spec, interpreter choice |
| `09-workflow` | How a milestone is broken into phases and plans |

## 2. Single ownership

**Every fact has exactly one home.** Other documents link to it; they do not
restate it.

This is the rule the whole system stands on, because the failure mode of
documentation is never "we didn't write it down" — it is two documents saying
different things and no way to tell which is stale. If a fact appears in two
places, one of them is already wrong or shortly will be.

Applying it:

- The palette lives in `04`. `theme.py` implements it. Nothing else names a hex.
- Requirement and decision identifiers are minted only in `01`. Everywhere else
  cites them: "per D-37", "F-29".
- A number that appears in prose — 48 kHz, 512 frames, 32 sources — is owned by
  one document and cited elsewhere, not re-derived.
- When a summary is genuinely useful (the overview's scope tables), it must
  link to the owner and must not add detail the owner lacks.

## 3. Identifiers

Four schemes, all monotonic, all permanent.

| Prefix | Meaning | Lives in | Current high-water |
|---|---|---|---|
| `F-n` | Functional requirement | `01-requirements` §Functional | F-56 |
| `N-n` | Non-functional requirement | `01-requirements` §Non-functional | N-6 |
| `D-n` | Decision, with its rationale | `01-requirements` §Decision log | D-94 |
| `QA-n` | A question asked during spec review, and its answer | `07-qa-archive` | QA-38 |

These four numbers are themselves the kind of fact §2 is about, so they are
asserted by `tests/test_docs.py` rather than maintained by hand.

Milestones use `M0`–`M9` and `S0`, defined in `06-roadmap`.

### The rules that make identifiers worth having

- **Numbers only ever go up.** The next decision takes the next free number
  regardless of what happened to D-12. (Deliberately not written here as a
  literal — a forward reference to an identifier that does not exist yet is
  the one thing §7's dangling-reference check cannot tell from a mistake.)
- **Never renumber.** A commit that renumbers identifiers invalidates every
  reference in every other document, every commit message and every code
  comment, and the damage is silent.
- **Never reuse a retired number.**
- **Supersede, do not delete.** A decision that is reversed keeps its row and
  gains a note naming the decision that replaced it. D-16 and D-32 are the
  worked example: bypass did not delete the stereo-downmix decision, it
  qualified it, and both rows say so.
- **A decision row states the rationale, not just the choice.** "Absolute
  imports" is a rule; "absolute imports, because the import graph is
  machine-checkable and that is what enforces N-5" is a decision. Rules without
  reasons get reversed by the next person who finds them inconvenient.

### When something needs an identifier

| Situation | Do |
|---|---|
| A choice was made between real alternatives | New `D-` |
| The product must do something observable | New `F-` |
| A measurable quality bar | New `N-` |
| A correction to an existing spec claim | Amend in place, and add a `D-` if the change was a judgement call |
| An implementation detail with one sensible option | Nothing. Write the prose. |

Not everything deserves a number. A log with 300 entries is not consulted.

## 4. Adding or extending a document

Prefer extending. A new top-level document is justified when a subject has an
owner that no existing document can plausibly claim — not when an existing one
has merely got long.

If one is warranted:

1. Take the next free two-digit number, kebab-case slug:
   `10-plugin-format.md`.
2. Add a row to `docs/README.md` and, if it changes how someone should read the
   set, a line to the reading order.
3. Link it from whichever canon documents refer to its subject.
4. State at the top what it owns, so §2 stays enforceable.

Numbers are never reassigned when a document is retired. A retired document
keeps its number and gains a header saying what replaced it.

## 5. Conventions

**Prose**

- Wrap at 80 columns. Diffs of reflowed paragraphs are unreadable, and a
  documentation system nobody will review is decoration.
- Say why, not only what. Most sections here end in a reason; that is the
  house style, not padding.
- Write the caveat where the reader will hit it, not in a footnote. The
  bypass time-alignment note sits inside the bypass section for exactly this
  reason.
- British or American spelling — pick one per document and be consistent
  within it. The existing set is British.

**Structure**

- ATX headings (`##`), never underlines. One `#` per file.
- Tables for anything enumerable: options, mappings, comparisons. Prose for
  anything with a because in it.
- ASCII diagrams in fenced blocks, monospace-aligned. No image files — they go
  stale invisibly and cannot be diffed.
- Fenced code blocks carry a language tag when the content is a real language,
  and none when it is pseudocode or a shell transcript.

**Links**

- Relative, and to the file: `[03-data-model.md](03-data-model.md)`. From a
  milestone directory, `../03-data-model.md`.
- Every cross-document reference is a link, not a mention. "See the data
  model" without a link is a dead end.
- Link identifiers to nothing — `D-37` is searchable and a link to
  `01-requirements.md` on every one of them would be noise.

**Symbols**, used sparingly and with fixed meanings:

| | |
|---|---|
| ⚠️ | A caveat that will otherwise be reported as a bug |
| ✅ | Complete |
| 🔴 | Blocking, or the risk milestone |
| ☑️ | Resolved by accepting a proposed default (archive only) |
| 🔧 | Deferred to a listening test or measurement |
| 📄 | Specified but not built |

## 6. Changing the canon

1. Change the document that **owns** the fact.
2. If a judgement was involved, add a `D-` row in `01` with the rationale.
3. Update every document that cites the changed fact — `grep` for the
   identifier and for the literal value.
4. Check the invariants in §7.
5. Commit the documentation change with the code it describes, when there is
   code. Otherwise commit it alone with a `docs:` subject that says what
   changed and why, not merely which files moved.

A spec correction says what was wrong and why, not just what it now says. The
crossfade rewrite in `05` is the pattern: it states that the previous claim was
incorrect and what the consequence would have been, because someone who read
the old version needs to know their mental model is stale.

## 7. Invariants

These must hold at every commit:

- Every `](NN-name.md)` link resolves to a file in `docs/`.
- Every `F-`, `N-` and `D-` cited anywhere is defined in `01-requirements.md`.
- Every `QA-` cited anywhere resolves to an entry in `07-qa-archive.md`.
- No identifier is defined twice.
- Every plan in a milestone's `plans/` has a phase of the same filename beside
  it (per [09](09-workflow.md)).
- The table in `docs/README.md` lists every numbered document, and no others.

These are enforced by `tests/test_docs.py` and run in CI with everything else,
so the list above is a guarantee rather than a checklist. It also checks two
things this section did not originally ask for: that the high-water marks in
§3 are current, and that no prefix's sequence has a hole in it — a gap means
an identifier was deleted by hand, which §3 forbids.

Both notes that were left for whoever automated it turned out to matter.
Fenced code blocks and inline code spans are stripped before matching, or
every template and every quoted pattern in this file and in `09` registers as
a broken link. And all four identifier prefixes are checked: the `QA-` rule
above was added after a hand check found a dangling reference in `07` that an
`F`/`N`/`D`-only pass had walked straight past.

One consequence worth knowing before it bites: an identifier written as a
*forward* reference — "the next decision will be …" — is indistinguishable
from a typo, and the check will reject it. Write the rule without the number.

## 8. Anti-patterns

Each of these has a real cost, which is why it is listed rather than assumed.

| Don't | Because |
|---|---|
| Restate a fact "for convenience" | Two copies, one stale, no way to tell which |
| Put a decision in a phase doc | Nobody searching the log will find it |
| Renumber identifiers to tidy the sequence | Silently invalidates every reference everywhere |
| Delete a reversed decision | Loses the reason it was reversed, so it gets re-proposed |
| Write a rule with no reason | Reversed by the next person who finds it inconvenient |
| Leave a document with no stated owner | §2 stops being enforceable and the set drifts |
| Add an image instead of an ASCII diagram | Goes stale invisibly, cannot be diffed |
| Let a status marker go stale | A stale ✅ is worse than no marker at all |
