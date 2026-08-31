# vault-kg-config.md field reference

One markdown file holding one fenced `json` block, at
`<vault>/vault-kg/vault-kg-config.md`. It is an ordinary file: edit it directly.
JSON rather than markdown tables because an agent is the primary editor, values
containing a pipe break tables, and a sorted JSON block gives readable diffs.

Everything here is optional. A vault whose config is never touched keeps
working: sections, search, the link graph and backlinks all need none of it.
Enrichment accumulates as structure is confirmed, and nothing degrades if it
never happens.

````markdown
# vault-kg-config

```json
{
  "ignore": [
    {"path": "archive/**", "reason": "superseded copies"}
  ],
  "profiles": [
    {"path": "journal.md", "profile": "log-dated", "date_from": "heading",
     "slots": {"Reflection": "authored", "Synthesis": "generated",
               "Metrics": "instrument"}},
    {"path": "sources.md", "profile": "dimension", "grain": "list-item",
     "group_by": "h2"},
    {"path": "generated/*.md", "profile": "generated", "weight": 0.2}
  ],
  "entities": [
    {"canonical": "Dana Okonjo", "type": "person", "time": "static",
     "aliases": ["Dana"], "note": "people/Dana Okonjo"}
  ]
}
```
````

Serialization is deterministic: fixed key order, entities sorted by canonical,
so adding one entity is a one-line diff. Omitted keys take their defaults.

One optional scalar sits beside the three arrays:

| key | meaning |
|---|---|
| `recency_k` | weight of recency in `search` scores, default `0.5`. Recency enters additively as `k * tier` (tier: newest dated entry of a note 1.0, oldest 1/N), so it reorders hits within `k` of each other on relevance and never buries a strong old match under a weak new one. `0` disables it. `search --recency-k` overrides it for one call. Written back only when set |

## ignore

| key | meaning |
|---|---|
| `path` | glob. `**` spans path segments, `*` stops at `/`, a pattern with no `/` also matches on basename |
| `reason` | free text, shown by `stats` |

Two other mechanisms do the same job, in this precedence order:

1. `kg-ignore: true` in a note's frontmatter
2. this `ignore` array
3. a root `.kgignore` file, one gitignore-style pattern per line

An ignored file is not read, chunked, indexed or counted, and `stats` reports
which rule matched. A link pointing at one gets status `ignored`, not
`unresolved`, so it does not pollute the broken-link worklist.

Exclusion is the cheapest quality lever there is. Indexing an archived snapshot
beside its live note means every search returns each answer twice, and the stale
copy sometimes wins on bm25.

## profiles

Resolved first-hit-wins: a note's own `kg-profile:` frontmatter, then this
array (longest matching glob wins, and every `path` row before any `kg_type`
row), then `reference`.

| key | applies to | meaning |
|---|---|---|
| `path` | all | glob, same syntax as `ignore`. A row takes `path` or `kg_type`, never both |
| `kg_type` | all | matches notes whose frontmatter `kg-type:` equals this value (case-insensitive). Demotion-only: `weight` must be `<= 1.0`, enforced loudly, because `kg-type` is corpus content and frontmatter never buys rank. Resolved after every `path` row, and only `profile`, `weight` and `description` are honored on such a row - a note self-selects into it, so it must not carry slot or date machinery |
| `profile` | all | `log-dated`, `reference`, `dimension`, `list`, `generated`, `hub`, `freeform` |
| `weight` | all | ranking multiplier, default `1.0` (`generated` defaults to `0.2`) |
| `date_from` | `log-dated` | `heading` (the default and only value today) |
| `date_order` | `log-dated` | overrides the inferred field order, e.g. `d-m-y` |
| `grain` | `dimension` | `list-item` |
| `group_by` | `dimension` | which heading level names the group, e.g. `h2` |
| `slots` | `log-dated` | maps a recurring child heading to a slot value |

`hub` is worth setting on any index or MOC note. Such a note links to
everything, so its edges otherwise inflate the degree prior for every note it
happens to list, and a two-hop `neighbors` walk routed through it returns the
whole vault. Marking it keeps it searchable while taking it out of both.

### Dates are inferred, not matched

The engine does not carry a list of date formats. It decomposes each heading at
a candidate level into digit runs and month names, takes the dominant shape, and
learns the field order from the corpus: the four-digit run is the year, and any
instance with a value above 12 fixes which of the remaining fields is the day.
An unusual layout is learned the same way a conventional one is.

Where nothing in the corpus disambiguates two numeric fields, year-first is read
as year-month-day and year-last as day-month-year. That guess is recorded in the
note's `kg-date-order` property and can be overridden with `date_order`.

### Slots

Five values, and nothing else is accepted: `authored`, `quoted`, `generated`,
`instrument`, `routine`. Aggregates (`themes`, `trends`) count `authored` by default
and `--slot` selects another.

`routine` is for procedural content the author did write but which is not prose: task
lists, checklists, standing agendas, recurring status blocks. It exists because such a
block is authored in the literal sense and skews every aggregate if counted as one. A
checklist restates the same nouns on every occurrence until the item is closed, so one
long-running open item surfaces as a theme of the whole period.

A section labelled with a slot is never rolled up into its parent, however
short. Swallowing a two-line `Metrics` block is exactly how instrument readings
end up counted as the author's own writing.

## markers

Vocabulary registration for the inline annotation layer (see
`references/annotations.md` for the grammar and effects). Registration only:
no per-marker effects, weights, or clamps exist here or anywhere.

| key | meaning |
|---|---|
| `marker` | the token, `[A-Z][A-Z0-9-]{1,31}`. Required. A core marker (NOTE, ANCHOR, SUPERSEDED, FOLLOW-UP, CLARIFY, DERIVED-FROM, EVENT) cannot be re-registered - the core vocabulary means the same thing in every vault |
| `description` | free text, shown by `stats` |

Custom markers are neutral: indexed, queryable through `annotations`, no
ranking effect. The array is serialized only when non-empty, sorted by
marker.

## entities

A gazetteer the user and agent co-maintain, not statistical entity guessing.
Glossary terms are entities with a different `type`.

| key | meaning |
|---|---|
| `canonical` | the name everything resolves to. Required |
| `type` | free text for your own taxonomy; nothing branches on it |
| `time` | `static`, `evolving`, or `<start>..<end>`. Blank means `static` |
| `aliases` | other surface forms; wikilink forms and frontmatter aliases fold in automatically |
| `note` | the note *about* this entity, or nothing |

`time` does the work:

- **`static`** - canonical and long-lived. Recency never demotes it and low
  mention frequency never filters it. This is the default because wrongly
  decaying a canonical entity hides a vault's best material, while wrongly
  holding a shifting theme steady is recoverable by reading dates.
- **`evolving`** - positions, themes, projects, where truth is the latest
  statement. `timeline` marks the newest mention current and the rest
  superseded. Disagreement across time is supersession, not error.
- **`<start>..<end>`** - a bounded event. `during <name>` returns the sections
  whose date falls inside, boundaries included.

Matching is case-insensitive on word boundaries, longest alias wins, and
possessives and plurals fold in. Mentions inside code fences do not count. An
alias claimed by two canonicals fails the ingest loudly rather than picking one.

### Aliases are same-ness; relations are not

Alias evidence is string-derived: a surname or initials of a multiword
canonical, an acronym, a near-spelling, a possessive or plural. **Never
co-occurrence.** Two entities that appear together constantly are related, not
identical, and co-occurrence evidence merges a person into the thing they
created. Relatedness is what the link graph and co-mention edges answer.

### Seeding

Where a vault has dimension-shaped files, the group headings are usually the
best free seed: each names an entity, it costs no curation, and they are
typically the same subjects the dated entries discuss. Note filenames and tags
are a weaker fallback - filenames are document names rather than entity names,
and tag vocabularies are usually thin.

After that, add an entity when a retrieval actually failed without it. Do not
work through a proposed list.
