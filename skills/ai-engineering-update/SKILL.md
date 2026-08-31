---
name: ai-engineering-update
description: The write path for the ai-engineering tooling corpus - keeps it current, deduplicated, and honest about what we have actually seen. Three jobs. DISCOVER new AI tools and fold them in ("refresh the AI tooling", "any new agent frameworks", "add these AI links"). VERIFY what changed ("check the catalog for staleness", "is X still current", "did that project get archived"). RECORD first-hand experience with a tool, good or bad ("note that X broke for us", "log that Y worked", "that framework's docs were wrong") - use it whenever a tool in the corpus is actually used and something is learned, not only during a maintenance pass. Wraps scripts/ledger.py and the deep-research skill.
---

# AI Tooling Refresh

The currency engine behind `ai-engineering`. It discovers new AI tooling, verifies
what changed, and folds findings into the catalog **deterministically and without
duplicates**. The hard parts - dedupe, classification, conflict resolution,
freshness - are handled by `scripts/ledger.py` in the `ai-engineering` skill; this
skill is the research-and-curate workflow around it.

## Why this exists

The corpus is maintained so that answers about AI tooling stay ahead of the model's
training data. Each refresh pass is what buys that, which is why every entry carries
a date and, where the project publishes one, a version.

The source catalog also grew by people repeatedly "finding" the same repo and
pasting it again. The ledger ends that: every URL has a canonical form and a
record. Before any link is added, it is checked against the catalog. New knowledge
accretes in **data** (`catalog.tsv`, `seed-sections.tsv`, `rules.tsv`), never by
editing code, so it scales without limit.

**Read `resources/data-contract.md` in the `ai-engineering` skill before adding a
file, a column or a store.** It states the canonical-URL join, which files are
generated, the tag vocabulary and its legacy spelling, and the conventions a new
store has to honor. Writing a store that does not join to the catalog produces an
island nothing else can see.

## The engine (read before using)

The `ai-engineering` skill's `scripts/ledger.py` (next to its SKILL.md; glob
`**/skills/ai-engineering/SKILL.md` if needed) - stdlib, deterministic:

| Command | Use |
|---|---|
| `ingest URLS… / --from FILE` | add new URLs; auto-dedupe (canonical form), auto-classify, log conflicts |
| `check --ttl N [--probe] [--limit K]` | liveness: flag rows unchecked in N days; `--probe` verifies the URL resolves (marks `dead`) |
| `check --claims [--section S]` | the claims queue: map rows whose ASSERTIONS are unverified. A URL resolving says nothing about whether its stars, license or maintenance status still hold |
| `verified URL...` | stamp `claims_checked` once verdicts have actually landed in the map |
| `sync-map-tags` | derive the `map` tag from `agent-stack-map.md`; run after adding or removing a map row |
| `set URL --sections 'a\|b'` | manually curate a URL; manual rows win conflicts |
| `render [--mark-stale --ttl N]` | regenerate `link-ledger.md` from the catalog (idempotent) |
| `seed --from-md FILE` | (re)scan a markdown bundle (e.g. the source KB file) into the catalog |
| `conflicts [--prune --ttl N]` | show the hot/cold conflict ledger; `--prune` ages out cold rows older than N days |
| `field-note URL --verdict V --finding "…"` | record first-hand experience; rejects an uncatalogued URL |
| `field-notes [URL] [--verdict V]` | read experience back |
| `render-notes` | regenerate `field-notes.md` from the notes (idempotent) |
| `decision / outcome / decisions` | record a committed stack slot and later stamp whether it held |

Data files (edit these, not the generated `link-ledger.md`):
- `resources/catalog.tsv` - source of truth, one row per URL.
- `resources/rules.tsv` - `domain → sections` auto-classify rules (add a row to teach a new domain).
- `resources/seed-sections.tsv` - `owner/repo → sections` for github/deepwiki repos (URL can't reveal category).

Engine-managed (do not hand-edit):
- `resources/_conflicts.tsv` - tracked hot/cold conflict ledger. Each conflict is one row
  (`seq, date, url, kind, resolution, state`); the **latest per URL is `hot`**, superseded
  rows go **`cold`**, and an identical re-conflict is de-duplicated (so recurring curated
  URLs never re-log). Read the `hot` rows to see current resolutions; `cold` rows are audit
  history, prunable by age (`conflicts --prune`) and always recoverable from git.

## Seed sources (where to look first)

Big aggregators worth re-scanning each pass - high signal, low noise:

- [awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps)
- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
- **Claude superpowers / Claude Code skill collections** (e.g. [affaan-m/ECC](https://github.com/affaan-m/ECC), formerly `everything-claude-code`; awesome-claude-code-toolkit) - match the owner, since same-name copies are common
- [Sumanth077/ai-engineering-toolkit](https://github.com/Sumanth077/ai-engineering-toolkit)
- **DeepWiki** - `https://deepwiki.com/<owner>/<repo>` lets you *interrogate any GitHub repo* conversationally; use it to verify what a repo actually does, its status, and its license before classifying it.

For anything moving (versions, GA/maintenance, license), use `WebSearch` or the
`deep-research` skill and cite the date. Never assert currency from memory.

## Recording experience (the third job)

Discovery and freshness both look outward at what other people publish. This one
records what we saw ourselves, and it outranks both, because it is evidence rather
than a claim.

```
ledger.py field-note <url> --verdict works|caution|broken|superseded \
  --finding "one line on the tool's behavior" \
  --scope "the condition it held under: version, OS, workload" \
  --evidence "commit, error string, or issue URL"
```

This does not wait for a maintenance pass. Record it at the moment it is learned:
when a recommended tool fails on install, when a library falls over at the size in
question, when a documented flag does not exist, when something works cleanly and
that is worth knowing.

**What belongs in a note** is the tool's behavior under a stated condition:
"install fails on Python 3.13", "OOMs above 50k documents". Environment as a
*condition* is the point of the `scope` field. Environment as *identity* stays out:
project names, machine names, and the names of locally installed tooling mean
nothing to another reader and rot when they are renamed.

Notes are append-only. A later `works` does not delete an earlier `broken`, because
a tool that failed at one version and is sound at the next is real history, and the
dates carry it. Run `ledger.py render-notes` to regenerate the readable view.

Stack decisions work the same way (`ledger.py decision` / `outcome`), and are
written by the scaffold skill at the end of its run rather than here.

## Workflow

1. **Scope.** "Find new tools in layer X", "check staleness", or "fold in these links".
2. **Discover.** Scan the seed sources and/or run `deep-research`/`WebSearch`. For each candidate repo, confirm via DeepWiki/web what it is, its status, and license.
3. **Dedupe-ingest.** Pipe findings through `ledger.py ingest`. Anything already known reports `unchanged` - that's the duplicate guard working. Genuinely new URLs are added; github/deepwiki repos with no `seed-sections` entry land in `triage`.
4. **Research every new row - never ingest-and-stop.** A pasted link is not
   knowledge until someone has read the project, and this applies with full force
   to the "fold in these links" scope, which otherwise skips step 2 entirely. Fan
   out parallel `researcher` subagents (bounded batches of 3-5 repos each, model
   pinned at spawn time), each writing dated, source-cited findings to a file the
   orchestrator names and returning a capsule. Each agent establishes, from live
   sources: what the repo actually does (not its marketing line), its status and
   license, what an AI engineer can learn from it - the transferable pattern,
   independent of adopting it - its relevance to the kinds of systems we build,
   and proposed section tags from the existing vocabulary. These findings are
   what drive classification and the human layer below; a row classified from
   its URL alone is a guess.
5. **Classify triage.** For each new `triage` row, add a `owner/repo → sections` line to `seed-sections.tsv` (or a domain rule to `rules.tsv`), then `set URL --sections '...'` to curate it. Re-`ingest` alone will not clear the row: ingest **unions** tags, so `triage` survives alongside the new sections (verified 2026-07-28). Use the section vocabulary already in the catalog.
6. **Freshness, on both axes.** `check --ttl 90 --probe --limit N` verifies that URLs still resolve; investigate any `dead` rows (renamed, moved, abandoned) and update or flag them. Then `check --claims --section <layer>` for the separate and more valuable pass: the map rows whose assertions are unverified. Take one section at a time, re-verify against a live source, correct `agent-stack-map.md` with the date, and stamp with `verified`. Do not stamp a row you did not actually check - the date is the whole value of the field.
7. **Resolve conflicts.** Read the **`hot`** rows of `resources/_conflicts.tsv` (or run `ledger.py conflicts`). Policy: **manual rows win**; otherwise sections are **unioned**; a dead/abandoned project is flagged in the map's cautions, not deleted. Record a one-line rationale for any non-obvious call. Occasionally run `ledger.py conflicts --prune` to age out old `cold` rows (git keeps the history).
8. **Update the human layer.** For entries that warrant analysis (not just a link), add/adjust rows in `reference-catalog.md` and, if opinion-worthy, `agent-stack-map.md` - with the date and a one-line currency note. Demote abandoned/closed paths to "inspiration only" rather than removing them.
9. **Render + report.** `ledger.py render` to regenerate `link-ledger.md`. Summarize: N added, N reclassified, N dead, N conflicts, and what changed in the opinion (new shortlist entrants, status changes).

## Guardrails

- **No bluffing.** Stars/licenses/GA status are claims about moving targets - verify and date them, or write `verify`.
- **Never hand-edit `link-ledger.md`** - it is generated. Edit the catalog/rules/seed and re-render.
- **Non-destructive.** Don't delete catalog rows for abandoned projects; set `status` and flag in cautions. History stays visible.
- **Determinism.** All outputs are sorted and idempotent - running a pass twice with the same inputs yields the same files.
