---
name: data-contract
description: How the files in this corpus relate to each other - the join key, which files are source of truth, which are generated, the tag vocabulary, and the conventions any new store must honor.
updated: 2026-07-27
---

# Data contract

This corpus is a set of files that key on each other. Anything added to it has to
honor the same joins, or it becomes an island that the rest cannot see. This
document states those joins so that the next change preserves them.

## Why the corpus exists

A model's knowledge of the AI ecosystem is fixed at training time and decays from
the first day it is used. Versions ship, licenses change, projects are archived,
governance moves, and a recommendation that was right nine months ago becomes
wrong without anything announcing it.

This corpus exists so that answers about AI tooling come from dated, verifiable
records rather than from that decaying memory. That is the whole point of it: to
be more current than the model reading it. Every convention below serves that
goal, which is why dates and versions are not decoration here. An undated claim
cannot be told apart from a remembered one, so it is worth nothing.

## The join key

Every entity in this corpus is identified by its **canonical URL**. Canonical form
is produced by `canon()` in `scripts/ledger.py`: the fragment is dropped, trailing
punctuation and a trailing slash are stripped, and scheme and host are lowercased
while the path keeps its case. Two URLs with the same canonical form are the same
entity and cannot both exist in the catalog.

Everything else joins on that key. A record whose URL is not in the catalog is
unreachable from the rest of the corpus, so writes that introduce one are
rejected rather than accepted and left dangling.

## Source of truth, and what is generated

Edit these:

| File | Holds |
|---|---|
| `catalog.tsv` | one row per URL; the spine everything joins to |
| `rules.tsv` | domain to sections, for automatic classification |
| `seed-sections.tsv` | owner/repo to sections, since a repo URL cannot reveal its category |
| `field-notes.tsv` | dated observations of what happened when a tool was used |
| `stack-decisions.tsv` | what was committed for a use-case shape, and whether it held |
| `agent-stack-map.md` | the opinion layer: comparisons, cautions, recommended architectures |
| `reference-catalog.md` | per-tool descriptions sorted by category |

The two append-only stores are written through `ledger.py`, never by hand:

- `field-note` and `field-notes` record and read first-hand experience. A note
  carries a verdict (`works`, `caution`, `broken`, `superseded`), the `scope` it
  held under, the finding, and evidence. Scope is what makes a note falsifiable
  rather than an opinion.
- `decision`, `outcome` and `decisions` record a committed stack slot and later
  stamp whether it `held`, was `replaced`, or was `abandoned`. The `use_case`
  field records the shape of the problem, never a project name, because shape is
  what makes the record reusable to a later reader.

Both reject a URL that is not already in the catalog. That rejection is what keeps
them joined to the spine.

Never hand-edit these, because a regeneration will discard the edit:

| File | Generated from |
|---|---|
| `link-ledger.md` | `catalog.tsv`, by `ledger.py render` |
| `field-notes.md` | `field-notes.tsv`, by `ledger.py render-notes` |
| `_conflicts.tsv` | written by the engine when a classification is superseded |

Classification is data, not code. Teaching the engine a new domain or repo is a
row in `rules.tsv` or `seed-sections.tsv`. Changing `ledger.py` to categorize a
specific tool is the wrong move every time.

## Section tags

A catalog row carries pipe-separated section tags drawn from the vocabulary
already in use: `frameworks`, `harnesses`, `memory`, `rag`, `vectordb`,
`ingestion`, `skills`, `serving`, `models`, `tuning`, `eval`, `codeintel`,
`security`, `frontend`, `learning`, `docs`, `papers`, `youtube`, `adjacent`,
`deepwiki`, `triage`, `map`. Reuse a tag before inventing one.

Two tags carry meaning beyond categorization:

- **`map`** means this URL also has a row in `agent-stack-map.md`. It is the join
  between the catalog and the opinion layer, and it is what scopes a freshness
  pass to the rows that actually inform recommendations. It is **derived, not
  hand-maintained**: `ledger.py sync-map-tags` reads the map and sets the tag to
  exactly the URLs found there. Never put `map` in a domain rule, which would tag
  every documentation subpage on that host and inflate the queue with pages that
  were never map rows.
- **`triage`** means the engine could not classify it. A triage row is unfinished
  work, not a category.

An older spelling, `harnesses(map)`, encodes the same `map` relationship inside a
single tag. Both spellings are currently present in `catalog.tsv`, `rules.tsv`
and `seed-sections.tsv`. New rows use the pipe form. Normalizing the old spelling
has to change all three files together, because the suffix is produced by the
classifiers and reappears at the next ingest if only the catalog is corrected.

## Every map row carries a URL

A row in `agent-stack-map.md` without a URL cannot be joined to the catalog, so it
is invisible to freshness checks, to recorded experience, and to anything else
keyed on the spine. Adding a map row means adding its URL and ingesting it.

Two kinds of row are exempt, and each is exempt for a stated reason rather than
by oversight:

- **Composite pointer rows** that name several tools at once and defer to another
  section for the detail. They describe no single entity, so there is nothing to
  key on.
- **Model rows.** A model identifier is not URL-addressable. Models are children
  of their provider row, which carries the URL, and no model gets a catalog entry
  of its own.

## Versions and verification dates

A claim about a moving target carries the date it was verified, and where the
project publishes one, its version. This is what separates a checked fact from a
recalled one, and it is what makes staleness visible instead of silent.

- Version and date belong in the row itself, in the form `v1.6.0, active
  (2026-07-27)`, so a reader sees the age of the claim next to the claim.
- `last_checked` in `catalog.tsv` records URL liveness only: that the address
  still resolves. It says nothing about whether the surrounding claims still
  hold. `claims_checked` is the separate axis, recording when the map's
  assertions about that tool were last verified against a live source. A row can
  be perfectly reachable and entirely out of date.
- Where a field has not been verified, it says `verify`. That is a real value
  with a real meaning, and it is always better than a plausible guess.

This convention governs claims about third-party tools. It is the opposite of the
rule for our own skill files, which carry no version numbers because git already
holds their history. Upstream versions are evidence about someone else's release;
a version on our own file is a number that drifts.

## Precedence when records disagree

Several files can each say a tool is unusable, and they will sometimes disagree.
Resolve in this order:

1. A dated first-party record of what happened when the tool was used.
2. A dated claim in the map.
3. The liveness probe.

First-hand experience outranks a project's own description of itself because it is
evidence rather than a claim. A probe result outranks nothing: it establishes only
that a URL resolves.

## Adding a new store

Any store added to this corpus honors the same shape:

- It joins on canonical URL, and it rejects a row whose URL is not in the catalog.
- It is append-only if it records observations over time. Contradicting records
  both survive with their dates, because a tool that was broken at one version and
  sound at the next is real history that a last-write-wins field would erase.
- It is TSV, git-tracked, and surfaced through a generated markdown view rather
  than read raw.
- Its writes go through `ledger.py`, so that canonicalization and validation
  happen in one place.

Append-only also merges cleanly. `catalog.tsv` is rewritten whole on every write,
which conflicts when two machines touch it at once; a store that only ever gains
rows does not have that problem.
