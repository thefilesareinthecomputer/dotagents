# Query strategy

Which instrument fits which shape of question. The engine documents its
commands in SKILL.md; this file is about choosing between them, and it exists
because every lesson in it was first learned by burning queries.

## Document classes decide the instrument

Most corpora hold a few recurring document classes, and a question aimed with
the wrong instrument at the wrong class wastes a search. The four that recur:

| class | profile | right instrument |
|---|---|---|
| append-only dated log (journal, incident log, changelog) | `log-dated` | `search` for content, `themes`/`trends` for aggregates, `trajectory` for "is this recurring", `timeline` for a registered entity |
| regenerated synthesis notes (agent- or template-written) | `generated` | retrievable through `search` but down-weighted and never counted as authored; treat hits as pointers back to the source material |
| mechanically flattened source material (a repo or export dumped into one huge note) | `freeform`, or `ignore` it | `sections` to locate the file's heading, then a line-range read. Full-text search over a megabyte of source returns noise |
| registers and rosters (tables or lists pretending to be prose) | `dimension` / `list` | `sections` then `read`. The group headings are entity seeds; `search` inside them mostly restates the heading |

A mixed corpus is normal; profile the dated files and leave the rest on
defaults, per SKILL.md's two-corpus-shapes section.

## When the graph is the wrong tool

- **Structured data inside fenced blocks.** YAML or JSON config in a flattened
  repo note is not searchable prose; FTS tokenizes it into noise. Locate the
  section with `sections`, read the lines, and hand the block to a parser.
- **Counts over every row.** Any question whose answer is an aggregate over a
  whole table ("how many notes carry X") is a parse or a `props`/`stats`
  query, not a search. If neither command answers it, write the three lines of
  Python; do not approximate it from a ranked list.
- **Negatives from bounded results.** A `TRUNCATED` result cannot support a
  claim of absence. Narrow the query or raise the limit until the status says
  `COMPLETE`, and only then reason about what is not there.

## The two-step is the intended pattern

Almost every real question is locate-then-read: `search` or `sections` yields
a section id and a line range; `read` returns the whole unit. Reading whole
notes because the first search was inconclusive is the failure mode the
section grain exists to prevent.

## Read the rung

`search` climbs a ladder - exact phrase, then all terms ANDed, then OR - and
reports which rung answered. An `all-terms` hit means the corpus genuinely
discusses the conjunction. An `any-term` hit means it does not: the results
share vocabulary with the question, and a conclusion built on them needs the
sections actually read first.

## After editing config, verify the ingest matched intent

A profile glob that misses writes no error; the note quietly takes the default
profile. After any profile or ignore change:

1. Re-ingest and compare `stats` counts (notes, sections, ignored) against
   what the edit should have changed.
2. Run `sections` on one note the rule should have caught - the unit grain
   shows whether the profile applied - and on one it should not have touched.
3. For an ignore rule, confirm the file appears under `ignored files` in
   `stats` with the rule named.

`ingest --keep-previous` before the edit makes the whole check one `diff`.
