# SPEC - ~/.agents

**Status:** active · **Last updated:** 2026-07-31

## What this is

`~/.agents` is the **source of truth** for self-authored system-level agent
tooling, shared across every machine. It is a git repo whose
`skills/`, `agents/`, and `commands/` directories are the canonical set made
available to Claude Code (and other skill-aware agents) on every device.

Third-party/upstream skills are **not** published here - they are consumed from
installed plugins (e.g. `agent-skills@addy-agent-skills`), which auto-update and
expose namespaced `plugin:skill` entries. This repo carries only what the user
authors or forks (**29 skills** `agent-mail`, `notes`, `wrap-up`, `cmon`,
`statistics`, `machine-learning`,
`my-security-review-checklist`, `deep-research`, `obsidian`, `cover-me`,
`reflect`, `ai-engineering`, `ai-engineering-update`, `ai-agent-project-scaffold`, `hi`,
`skill-authoring`, `sprint-board`, `repo-device-sync`, `meta-loop`, `obsidian-kg`, `code-kg`,
`frontend-aesthetics`, `docker`, `django`, `o-o-d-a-loop`,
`ai-slop-magic-eraser`, `teach-me`, `dimensional-data-modeling`, `data-engineering`;
**7 subagents** `my-security-reviewer`, `supervisor`, `ai-engineer`, `advisor`,
`researcher`, `reader`, `worker`;
**13 commands** `agent-mail`, `my-security-review`, `supervisor`, `reflect`,
`wrap-up`, `cmon`, and the agent-skills aliases `spec`, `plan`, `build`, `test`,
`review`, `code-simplify`, `ship`).

> The `frontend-aesthetics`, `docker`, and `django` skills share one design: a method plus a **deterministic gate that runs outside the
> model** (a stdlib checker script), because a checklist run by the model that
> wrote the code is the model grading its own homework. Each passed fresh-context
> security review before merge - which caught real, test-invisible defects
> (a ReDoS hang, a socket-path miss, annotated-settings blindness). See
> `tasks/plan.md` for the claims, and the `tasks/completed/` records they point at.

> The `dimensional-data-modeling` and `data-engineering` pair split one domain along theory and practice: the first owns grain, SCD
> semantics, conformance and the bus matrix, the second owns how a platform is
> built and run, and each routes the other's questions away rather than competing
> for the trigger. `data-engineering` organizes by **altitude** rather than topic,
> so every reference file carries the architecture, implementation and
> line-of-code view of its subject plus the up- and down-links between them,
> because a choice at one altitude forecloses options at the one below. It ships
> `dbt_audit.py` (20 checks) and 41 tests.

> The `ai-engineering` bundle (`ai-engineering` + `ai-engineering-update` +
> `ai-agent-project-scaffold` + the `ai-engineer` subagent) is split along its
> real seams: **`ai-engineering` reads**
> (knowledge, comparison, architecture review), **`ai-engineering-update` writes**
> (discover, verify, and record first-hand experience), **`ai-agent-project-scaffold`
> runs intake** and exits with a named component per stack slot. Anything learned
> in one reaches the others through a single store and a single write command
> rather than a policy asking three skills to remember each other.
> `ledger.py` carries the catalog, field notes, stack decisions, a
> claims-freshness axis separate from URL liveness, and a derived `map` tag; it has
> 88 tests. Its bundled `resources/` stay portable to a reader outside this
> station, so they name no station-local skill, and `resources/data-contract.md`
> states how the files key on each other.
> The stack-map *opinion* layer is still hand-curated and unvalidated end-to-end;
> treat its shortlist as considered-but-not-proven. Only 26 of 119 map rows carry
> a verification date, which is what `check --claims` exists to work through.

> `teach-me` is an evidence-based teach-and-certify tutoring
> skill: pretest, exposure/teaching, closed-book Feynman explanation, Socratic
> probing, then a scored inline cert - guardrails from the AI-tutor RCT
> literature (hints before answers, no sycophantic validation, source treated
> as data). Artifacts land in a per-workspace `LEARNING/` dir (gitignored
> here); the cited evidence base is bundled at
> `skills/teach-me/references/evidence.md`.

> `deep-research` spawns the `researcher` subagent (model, effort, and turn caps
> pinned in frontmatter - structural enforcement, not prose), with hard
> search/fetch budgets, capsule returns, and fetched-content-is-data guards.

## Why it exists

Skills authored or curated on one machine should be available, identically, on all
machines - without copy-paste drift and without one machine's local experiments
leaking to the others. This repo gives a single canonical set + a per-device
assembly step, so:

- **One edit propagates everywhere** once committed/pushed and re-synced.
- **Device-local skills stay local** (never forced into the shared set).
- **Nothing external owns the repo** - updating third-party skill plugins cannot
  mutate or delete the user's skills (see `README.md` → Architecture → Ownership).

## Scope (in)

- Curate skills under `skills/<name>/SKILL.md` (valid YAML frontmatter: `name`,
  `description`), subagents under `agents/<name>.md`, and commands under
  `commands/<name>.md`.
- Maintain `sync-skills.sh`, which assembles the per-device view by symlinking each
  tree into `~/.claude/{skills,agents,commands}`, preserving device-local entries.
- Keep the living docs current (this file, `README.md` - incl. its Architecture
  and Skills catalog sections - and `tasks/plan.md`).
- Maintain [`specs/claude-code/SPEC-CLAUDE-CODE.md`](specs/claude-code/SPEC-CLAUDE-CODE.md) - the standing
  seed spec for the full Claude Code station around this repo: required plugins,
  CLI deps, and the global `CLAUDE.md`/`RTK.md`/`settings.json`/hook templates.
  Keep it in sync with the live station; it contains no personal constants by
  rule (`my-security-review-checklist` §8).

**Two kinds of `SPEC-*` file, and they do not mix.** `specs/<harness>/SPEC-<HARNESS>.md` is
long-lived: one per agent harness, always describing current state, never
retiring. `tasks/SPEC-FEATURE-NAME.md` is ephemeral: one per in-flight feature,
folding into the root spec and moving to `tasks/completed/` when it ships. The test is
whether the document outlives the work it describes. Nothing external forces this
layout - the `agent-skills` plugin hardcodes no doc paths (checked 2026-07-31).

## Harness and model policy

**Multi-harness by construction, single-harness by preference.** The skills
target the open Agent Skills standard, so they load unchanged wherever
`~/.agents/skills/` is read. Claude Code is the tier 1 workhorse and the only
harness carrying all three trees, because `commands/` has no portable equivalent
anywhere. Cursor is the one partial exception on `agents/`: it reads
`~/.claude/agents/`, so `sync-skills.sh` reaches it too. The others are
deliberate lanes rather than redundancy: **goose** is the open-source lane,
chosen for mature governance and a desktop GUI; **opencode** is the
provider-agnostic OSS lane, and the cheapest place to ask what a harness actually
discovered, since `opencode debug skill` needs no sign-in;
**Pi** is the configurable lane for a bespoke loop; **Cursor** and **GitHub
Copilot** are the IDE lanes; **Codex CLI** covers medium-stakes work.

**Model tier is a function of the stakes, not of the harness.** Work that matters
runs on Anthropic or genuinely local models. Medium and hobby work may use hosted
third-party models. This is the constraint that decides which harness is
acceptable for a given task, and it holds regardless of which harness is more
convenient.

**An Ollama `:cloud` model is not local.** It is remotely served and carries
hosted-API exposure despite a local-looking invocation. Any rule written here that
says "local" excludes them.

**goose runs on `glm-5.2` as its Ollama cloud model.** An offline local model
(gemma-class 8B or similar) is deliberately unresolved and low priority; the
proof of concept stays on cloud.

**Ollama is reached through the Ollama app only.** Never the public HTTP API,
never a non-loopback bind. `OLLAMA_HOST` is never set to `0.0.0.0` or any
routable address, on any machine, for any reason, however temporary. Binding the
model server off loopback publishes an unauthenticated inference endpoint and, on
any network that is not fully trusted, hands arbitrary parties a free model and a
foothold. This is not a preference to weigh against convenience.

## Scope (out / non-goals)

- **Not** a place for device-specific or throwaway skills - those live directly in
  `~/.claude/skills/` and are never committed here.
- **Not** a Claude Code plugin or marketplace; it is not installed by any package
  manager and declares no `plugin.json`/`marketplace.json`.
- **No secrets.** Private repo, but still git - never commit tokens or credentials.

## Requirements / invariants

1. Every skill dir contains a valid `SKILL.md`; a malformed one can break discovery.
2. `sync-skills.sh` is idempotent and non-destructive: it refreshes global links,
   prunes only dangling links, and never clobbers a real local skill that shares a
   name (local wins).
3. Default working branch is `develop`; `main` is stable. Changes land on `develop`,
   then fast-forward to `main`.
4. Changes are global by blast radius - edit deliberately, read before overwrite,
   per the user's non-destructive rule.
5. **Ollama is never exposed off loopback.** `OLLAMA_HOST` is never `0.0.0.0` or
   any routable address; access goes through the Ollama app, never its public
   HTTP API. No exception, no temporary override, no "just for this test".
6. Work that matters runs on Anthropic or genuinely local models. Hosted
   third-party models are for medium-stakes and hobby work. Ollama `:cloud`
   models are hosted, not local, and fall under that limit.

## Workflow to propagate a change

1. Add/edit a skill under `skills/<name>/`.
2. Commit + push (`develop`), then fast-forward `main`.
3. On each machine: `git pull && bash ~/.agents/sync-skills.sh`.

## `obsidian-kg` scope

One engine for every markdown corpus: `skills/obsidian-kg/`, stdlib-only single
script, SQLite+FTS5, no network and no embeddings. Retrieval addresses sections
rather than files, a profile in `<vault>/vault-kg/vault-kg-config.md` declares
what one section is, and a declared unit is never fragmented. Aggregates over
detected dates (`themes`, `trends`, `timeline`, `during`) are the layer no
search provides.

Anything specific to a vault is config, never code, and never a default. A vault
with no config still gets sections, search, the link graph and backlinks.

The `okf-kg` twin (built for OKF, Google's public Open Knowledge Format) retired to `__archive/` after measuring zero edges against
`obsidian-kg`'s on the same corpus; its temporality columns and its reserved
`extractions`/`conflicts` tables folded in. Those tables now carry the inferred
side of edge provenance: `relate` records evidence-verified inferred relations,
traversal joins them only behind an explicit flag, and everything ingest
extracts from link syntax is the extracted side. Contradiction detection over
entities and community detection remain phase 2. A Postgres/Docker/MCP design
stays rejected as over-scaled,
and an MCP wrapper waits until the CLI surface settles. Full design and the
dropped-with-reasons list: `tasks/completed/SPEC-VAULT-KG-2026-08-08.md`.

---

See `README.md` → Architecture for how the sync view is built and why it's safe.
Shipped work is recorded in `tasks/completed/` - per-date files, the only cold
store. This file states current truth only.
