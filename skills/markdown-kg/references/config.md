# markdown-kg-config.json field reference

The config is one JSON object at `<vault>/.kg/markdown-kg-config.json`.
A vault not yet migrated has it as one fenced `json` block in a legacy markdown file, `markdown-kg/markdown-kg-config.md` or `vault-kg/vault-kg-config.md`, which the engine keeps using in place; a legacy file with text but no `json` block is an error, never an empty config.
It is an ordinary file: edit it directly.
JSON because an agent is the primary editor, values containing a pipe break markdown tables, sorted JSON gives readable diffs, and a malformed file fails loudly instead of dropping its rules.

Everything here is optional. A vault whose config is never touched keeps
working: sections, search, the link graph and backlinks all need none of it.
Enrichment accumulates as structure is confirmed, and nothing degrades if it
never happens.

```json
{
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

Serialization is deterministic: fixed key order, entities sorted by canonical,
so adding one entity is a one-line diff. Omitted keys take their defaults.

Two optional scalars sit beside the arrays:

| key | meaning |
|---|---|
| `recency_k` | weight of recency in `search` scores, default `0.5`. Recency enters additively as `k * tier` (tier: newest dated entry of a note 1.0, oldest 1/N), so it reorders hits within `k` of each other on relevance and never buries a strong old match under a weak new one. `0` disables it. `search --recency-k` overrides it for one call. Written back only when set |
| `link_resolution` | `obsidian` or `relative`: how a markdown link that misses its relative path is read. When it is unset, the engine detects the mode: a vault with an `.obsidian/` folder is `obsidian`, any other tree is `relative`. See [Markdown links](#markdown-links) |

Four more arrays are optional, and an absent one is empty: `markers`, `entity_sources`, `relations` and `holdback`.
A config written before they existed loads exactly as it did.

`holdback` is a list of gitignore-style globs matched against repo-relative POSIX paths,
for files the repo tracks but never publishes, such as `["/tasks/", "/_RESEARCH/"]`.
As in gitignore, a leading `/` anchors a pattern at the repo root, a pattern with no other `/` matches at any depth, and a trailing `/` means the folder and everything under it.
The link check treats a held-back file as not committed, so a committed note that links to one is `forbidden`.
It is read per graph, when a command runs, and `config` echoes it.
Only a repo that tracks files it does not publish needs it: an untracked or gitignored file is already not committed.

## Checking an edit

`config <vault>` reports what each row matched: notes per `profiles` row, sections per entity, notes and derived entities per `entity_sources` row, links per `relations` field, and annotations per custom marker.
A row that matched nothing is a warning, never an error, because the config is allowed to be ahead of the corpus.
The command writes nothing, and it exits nonzero only when the file itself is malformed.

## Ignoring files: .kgignore

Exclusion is not in this config. Both engines keep a file out of the graph when
a rule in a `.kgignore` at or below the vault root matches it, in git's syntax:
`#` comments, `!` re-includes, a trailing `/` matches folders only, a leading or
inner `/` anchors the pattern to its file's folder, `*` stops at `/` and `**`
spans folders. The last matching rule wins. `.gitignore` is not read, since the
graph may need what git leaves out of a commit, and rules above the root are
never read, so the graph is the same on every machine. Put a reason on the line
above a pattern as a `#` comment.

An ignored file is not read, chunked, indexed or counted, and `stats` reports
which file and line matched. A link pointing at one gets status `ignored`, not
`unresolved`, so it does not pollute the broken-link worklist. A config that
still has an `ignore` array is refused with an error, never half-read;
`migrate` moves a legacy config's rows into `.kgignore`, dropping and reporting any row that names the legacy folder itself.

Exclusion is the cheapest quality lever there is. Indexing an archived snapshot
beside its live note means every search returns each answer twice, and the stale
copy sometimes wins on bm25.

## profiles

Resolved first-hit-wins: a note's own `kg-profile:` frontmatter, then this
array (longest matching glob wins, and every `path` row before any `kg_type`
row), then `reference`.

| key | applies to | meaning |
|---|---|---|
| `path` | all | glob: `**` spans folders, `*` stops at `/`, a pattern with no `/` also matches on basename. A row takes `path` or `kg_type`, never both |
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

## entity_sources

An `entity_sources` row derives entities from notes that already have a page each, which is the shape of an LLM-wiki vault (`entities/`, `concepts/`) and of any vault that types its notes with `kg-type`.
One row covers a whole folder, so the registry tracks the vault's pages without a hand-written row per page.

```json
"entity_sources": [
  {"path": "entities/*.md", "type": "equipment"},
  {"kg_type": "concept", "type": "concept", "time": "evolving"}
]
```

| key | meaning |
|---|---|
| `path` | glob, same syntax as a `profiles` path. A row takes `path` or `kg_type`, exactly one |
| `kg_type` | matches notes whose frontmatter `kg-type:` equals this value (case-insensitive) |
| `type` | copied to each derived entity's `type` |
| `time` | `static` (default) or `evolving`. A span belongs in a hand-written `entities` row |

For each matching note the title is the canonical name, the file name and the frontmatter `aliases` become aliases, and `note` is the note itself.
A note resolves to one row the way profiles do: the longest matching `path` glob, then a `kg_type` row.

A hand-written `entities` row always wins.
A derived name is left out, and recorded, when a hand-written row already names the note, when another entity already claims the name, or when the name is shorter than three characters.
Derivation can never fail an ingest, because note content must never be able to fail one; `config` lists every name that was left out and why.

Point a row at pages that are curated, such as an entities folder.
A glob over a whole vault turns every note title into a gazetteer entry, which is the batch-curated registry the Seeding section warns against.
It also costs ingest time: each entity name is one pass over every section, measured at about 16 ms per megabyte of vault text per name, so 3,000 names over a 5 MB vault add about four minutes to an ingest.

## relations

A link written under a name is a typed relation, and the engine records that name with no config at all.
The name is either a frontmatter key (`up: "[[Parent]]"`, a list of links, or a markdown link) or an inline field (`up:: [[Parent]]` on its own line or list item, `[up:: [[Parent]]]` or `(up:: [[Parent]])` mid-sentence).
`fields` lists them. `tags`, `aliases` and `cssclasses` are never fields, and neither is anything in code or in a comment.

A `relations` row adds the name of the relation read backwards, which is the one thing the corpus cannot state:

```json
"relations": [
  {"field": "up", "inverse": "down"},
  {"field": "maintained-by", "inverse": "maintains"}
]
```

| key | meaning |
|---|---|
| `field` | the field name, normalized: lowercase, spaces as hyphens. Required |
| `inverse` | the label `fields --note` shows on an inbound link under this field |

`config` warns on a declared field no note uses, and lists the fields in use that have no row.

## Markdown links

Standard markdown links resolve relative to the file that wrote them, or from the vault root with a leading `/`.
A target with no extension resolves when that path names a note.
Reference-style links (`[text][label]` with a `[label]: target` definition) resolve the same way.

In `obsidian` mode, a link that misses its relative path and was not written as an explicit `./`, `../` or `/` path is read the way Obsidian writes markdown links.
The engine matches it by file name anywhere in the vault (the "shortest path" link format) or by path from the vault root (the "absolute path in vault" format).
When two notes have that name, the link is `ambiguous` and the engine does not guess between them.
In `relative` mode such a link stays `unresolved`, because a renderer that reads link paths relative to the file does not follow it.
