---
name: ai-engineering
description: Authoritative source of truth on AI tooling and how to choose it - the knowledge behind building AI agents and AI systems. Use when choosing between agent frameworks, harnesses, memory, RAG, ingestion, serving or eval components; when weighing an architecture for an agent/LLM system; when asked "what's the current state of X", "what are my options for Y", "is Z still maintained", or "what license is Z"; and when reviewing whether an AI design honors sound engineering practice. Answers come from the bundled dated corpus, not from training memory. Standing up a new AI project or adding an AI subsystem to an existing repo goes to ai-agent-project-scaffold; updating the corpus goes to ai-engineering-update; general engineering discipline to agent-skills; MCP servers to build-mcp-server.
---

# AI Engineering

The knowledge layer for **AI systems: what exists, what it costs to adopt, and
which component fits a given job - especially OSS.** It carries a curated,
deduplicated catalog of the agent-stack ecosystem and an opinionated map for
choosing components.

This is the read path. It advises; it does not run intake or generate repos.

**Read the bundled resources instead of answering from training memory.** Versions,
licenses, maintenance status and governance all move after a model's training data
is fixed. The resources below are dated and verifiable, which is what lets them be
more current than the model reading them.

## Scope - and what this skill is NOT

**This skill owns:**
- **Stack selection** - picking framework / harness / memory / retrieval / ingestion / serving / frontend components, with the tradeoff that decides each.
- **Component judgment** - what a tool is for, what it costs to adopt, where it breaks, what its license obliges.
- **Tooling currency** - being right about what's GA, abandoned, source-available-with-conditions, or newly relevant.
- **Architecture review** - whether a proposed AI design honors the engineering principles below.

**This skill is the read path. Three neighbours own the rest:**
- **Standing up a project** - intake, committing to a full stack, generating the repo → `ai-agent-project-scaffold`. That includes adding an AI subsystem to an existing codebase. Advising on components stays here; the moment the job is to *build* one, it belongs there.
- **Changing the corpus** - folding in new tools, verifying what changed, recording what we learned by using something → `ai-engineering-update`. It owns every data file under `resources/`.
- **Deep web research** on a tool → `deep-research`, then offer to fold the result in via `ai-engineering-update`.

**And general engineering is not reimplemented here:**
- Spec / plan / build / test / review / ship → `agent-skills` (`/spec`, `/plan`, `/build`, `/test`, `/review`, `/ship`). Use this skill to choose the AI components, then those to build them well.
- **Building an MCP server** → the system's `build-mcp-server` / `build-mcp-app` skills (official `mcp-server-dev` plugin) and `plugin-dev`'s `mcp-integration`. Do not hand-roll MCP scaffolding here.
- **A fresh-context build pass** → delegate to the `ai-engineer` subagent, under the guard below.

**Delegation guard (applies wherever this skill hands work to `ai-engineer`).** Delegate
only genuinely heavy, *new* build/scaffold work, and only as a **one-shot task with a
complete, self-contained spec** - then verify the result. Never watch a subagent iterate
on a single artifact, and never delegate small or iterative edits: those stay inline in
your own context (a background subagent grinding pass-after-pass on one file is the
failure mode, not the tool). If a delegated pass comes back wrong twice, stop delegating
and finish it inline.

If a request is really general software engineering with an AI label on it, say so
and route to the right `agent-skills` skill rather than absorbing it here.

## Resources (bundled)

Read these before answering - they are the source of truth, not your training memory:

- **`resources/agent-stack-map.md`** - opinionated comparison tables (frameworks, harnesses, memory, retrieval, skills, ingestion, tuning/RL, self-improvement, and the NVIDIA NeMo stack in Section J), recommended architectures by use case, current shortlist, and licensing/security cautions. *Start here for "what should I use for X".*
- **`resources/reference-catalog.md`** - every tool/repo/doc sorted by category, with confident one-liners and a to-triage bucket. *Start here for "is there a tool for Y / where are the docs".*
- **`resources/link-ledger.md`** - the alphabetized, deduplicated record of **every URL** (578) already folded in. **Always grep this before adding a new link** - if it's here, it's already covered. Prevents re-discovering the same resource.
- **`resources/data-contract.md`** - how these files key on each other: the canonical-URL join, which files are source of truth versus generated, the section-tag vocabulary, the version-and-date convention, and the precedence order when records disagree. *Read before adding a file, a column, or a store to this corpus, so the new thing joins to the rest instead of becoming an island.*
- **`resources/engineering-principles.md`** - the house doctrine every recommendation must honor: offline-first/stdlib-first defaults, determinism over heuristics, capability-gates-behavior (config over prose), evidence over claims, fresh-context adversarial review, cost-tiered orchestration, untrusted-input-is-data, territorial scope over flags, portability (no personal/environment constants), non-destructive defaults, CLI-first (MCP only for shell-less clients), spec-first docs-as-truth, eval-gated tooling. *Read when designing any system or reviewing an architecture - a stack choice that violates these is wrong even if the tools are good.*

> Currency caveat: stars/licenses in the map are point-in-time (≤ 2026-06). For a
> live answer on a moving target, run `ai-engineering-update` or `deep-research` and
> cite the date - never present a stale field as current.

## How to use it

### Advising on a stack
1. Read `agent-stack-map.md`; identify the layers the use case needs (orchestration / memory / context / ingestion / serving / frontend).
2. Lead with the **architecture decision and rationale**, then components. Name the bill: cost, complexity, lock-in, license, skill gap.
3. Honor stated constraints (existing footprint, no-lock-in mandate, local-first). Default to OSS / portable when no lock-in mandate exists; default to the user's footprint for active projects.
4. Flag any **license trap** (AGPL, SSPL, source-available-with-conditions) and any **maintenance/security** caution from the map.
5. If the map is stale or the tool isn't covered → `deep-research`, then offer to fold the result in via `ai-engineering-update`. Never bluff a version, GA status, or star count.

### Answering "what are my options for X"
Survey the relevant layer in `agent-stack-map.md` with the cloud-native / cross-cloud / OSS framing **before** recommending one path. Then recommend, opinionated, with the tradeoff that decided it.

### When the advice gets tested in the same session
A recommendation from this skill that then fails in practice - the install breaks,
the license turns out to be incompatible, the library falls over at the size in
question - is first-hand evidence, and it is worth more than anything the corpus
currently says about that tool. Record it before moving on:

```
ledger.py field-note <url> --verdict broken --finding "..." --scope "version, OS, workload"
```

Verdicts are `works`, `caution`, `broken`, `superseded`. The `scope` is what makes
the note falsifiable rather than an opinion. Notes are append-only, so a later
success does not erase an earlier failure and the dates carry the history.

### When records disagree
Several files here can each say a tool is unusable, and they will sometimes
conflict. Resolve in this order:

1. A dated field note - what happened when it was used.
2. A dated claim in the map.
3. The liveness probe, which establishes only that a URL resolves.

First-hand experience outranks a project's description of itself because it is
evidence rather than a claim.

## Maintenance contract

- `link-ledger.md` is **generated** from `resources/catalog.tsv` by `scripts/ledger.py` - never hand-edit it. To add a resource, run `ledger.py ingest <url>` (it canonicalizes + dedupes + classifies + logs conflicts), then `ledger.py render`. Re-adding a known link reports `unchanged` - that's the duplicate guard that the original bundle lacked.
- Classification is data-driven: domain rules in `resources/rules.tsv`, repo→section map in `resources/seed-sections.tsv`. Teaching a new category is a data edit, not a code change - it scales without limit.
- The full discovery + freshness + conflict loop (seed aggregators, DeepWiki, `deep-research`, `check --probe`) belongs to the **`ai-engineering-update`** skill, which owns this engine.
- For a heavy build/scaffold pass, delegate to the **`ai-engineer`** subagent.
- **The corpus stays portable.** `resources/*` describes the outside world and is read by people who do not share this environment. Keep environment-specific skill, agent and config names out of it - an entry saying a tool "overlaps my X skill" or "is where our house rules came from" means nothing to another reader and rots when X is renamed. Overlap between the catalog and locally-installed tooling belongs in a separate map keyed on catalog URL, not in prose beside an entry. Routing to sibling skills stays here in SKILL.md, where declaring boundaries is the point.
