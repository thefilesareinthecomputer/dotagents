# ADR 0001: Standard `docs/`, `tasks/` and `kb/` layout for repos

Status: Accepted (2026-11-26; amended the same day: the vault moves from `docs/kb/` to `kb/`)

Decision owner: user

Contributors: .agents

## Context

Repos built with this toolkit keep agent working state and formal documentation side by side.
Specs, plans, backlogs and session records all sit in `tasks/`, and some repos also have a `docs/` folder and a project vault.
Seeding `project-knowledge-vault` into a code repo that already has `SPEC.md`, `tasks/` and `docs/` showed the cost.
Nothing says which vault roles give way to the repo's own files, ADRs land in a sibling folder outside the repo,
and the skill's docs contradict its code in four places.

The vault skill has to serve three deployment shapes:

- **A.** One vault in a code repo, with its own graph.
- **B.** A workspace of co-located project vaults (`<root>/PROJECTS/<NAME>/`).
- **C.** A knowledge or research engine queried across one, some or all of those vaults.

## Decision

Repos use three lanes:

```text
README.md  AGENTS.md  CHANGELOG.md  LICENSE   # root: tools and hosts look for these here
docs/                                         # graduated, verified knowledge (tracked)
  SPEC.md  ARCHITECTURE.md
  adr/NNNN-title.md
  designs/
  research/
tasks/                                        # the agent's queue (usually untracked)
kb/                                           # the project's working vault (untracked by default)
```

- `docs/` is the repo's formal, committed knowledge. Only durable design lives there.
- `tasks/` is the agent's working queue: plan, todo, backlog, completed records,
  and in-progress feature specs (`tasks/SPEC-<NAME>.md`). It is gitignored in public repos.
- `kb/` is the flat project vault: the user's run sheet, the `notes-*` logs, learnings, questions,
  and all four `user-stories*` notes together. It is untracked by default and tracked in a private team repo.
  The run sheet holds the user's steps; the agent's steps stay in `tasks/`.
- The vault is a top-level `kb/`, not `docs/kb/`, because it is working state rather than graduated knowledge,
  and a `docs/` graph would otherwise have to ignore it.
- `docs/tasks/` is rejected: it would mix agent scratch work into formal docs.
- `CHANGELOG.md`, `LICENSE` and `README.md` stay at the root, where release tools and GitHub expect them.
  `CONTRIBUTING.md` and `SECURITY.md` may sit at the root, in `docs/` or in `.github/`.
- Existing repos move to the layout when they are next worked on, not in one sweep.
- In this repo, only the root `SPEC.md` moves under `docs/`; `specs/` stays for now.

### Graduation

Content moves one way, into `docs/`, and only once it is real: built and signed off, or verified, and approved by the user.
A feature spec in `tasks/` is built and signed off, moves to `tasks/completed/`, and its durable facts
graduate into `docs/` as a `SPEC.md` section or an ADR.
A verified learning in `kb/` graduates into `docs/` when the user approves.
`notes` and `wrap-up` propose graduations and write into `docs/` only on the user's yes.
Private in-progress specs therefore stay out of anything published, and `docs/` needs no private area.

### Link direction

Links point toward `docs/`, never away from it. `kb/` and `tasks/` may cite `docs/` and each other;
`docs/` cites only `docs/` and code.
A committed file never links to, or names by path, a specific uncommitted file, since that link is dead for every clone.
Naming a lane as a folder is allowed. markdown-kg reports a link from a committed file to an uncommitted
or held-back file as `forbidden`, and in a repo with a `docs/` graph the commit hook blocks it.

### Graphs and federation (answers shape C)

markdown-kg keeps one graph per lane or project vault (`docs/.kg/`, `kb/.kg/`, `PROJECTS/<NAME>/.kg/`)
and never merges lanes into one index. Queries join them at read time:

- a discovery command lists every graph around a path, each named by its path from the workspace root;
- the search and link commands state which graphs they searched and which they did not, so a miss is never read as absence;
- `search --all` runs each graph's own search and fuses the results by reciprocal rank, since bm25 scores
  are relative to each corpus and cannot be compared;
- sibling graphs are opened read-only.

code-kg keeps one graph per repo.

The model is written once for every skill in `skills/project-knowledge-vault/references/lanes.md`.

## Rollout order

1. One code repo pilots the layout (done; its findings shaped the amendment above).
2. Tests and smoke tests, then the setup is put through its paces.
3. The skills change.
4. The changes are pushed, so every station can pull and apply them.

## Consequences

- Global `AGENTS.md` says that durable design lives in `docs/` and in-progress feature specs in `tasks/`.
- Every skill that names a `tasks/` path is checked against that line; feature-spec discovery
  (`tasks/SPEC-*.md`) keeps working, and graduation into `docs/` becomes a step in `notes` and `wrap-up`.
  Skills that read or write `tasks/` files: `goldfish`, `notes`, `meta-loop`, `sanitize`, `skill-authoring`,
  the `spec` command, `hi`, `wrap-up`, `focus`, `agent-team`, `agent-review`, `agent-conference`,
  `sprint-board` and `support-local`.
- `project-knowledge-vault` gains a repo mode for shape A: it seeds `kb/`, the repo's own files win,
  only missing roles are seeded, deliverables go to `docs/adr/` and `docs/designs/`, and no `-DELIVERABLES`
  sibling is made inside a repo. Shape B keeps the sibling.
  SKILL.md opens with a table of the three shapes, and the four doc and code contradictions are fixed.
- markdown-kg gains graph discovery, a scope line on every read command, link statuses with a `forbidden`
  check, and cross-graph search.
- A repo with a vault at `docs/kb/` moves it to `kb/`.
- A planned `/repo` skill sets up this layout in a new repo (`baseline`) and reports drift from it (`audit`).

## Open questions

1. **The `specs/` folder name.** It holds per-harness station specs and may be renamed (`harnesses/` or similar).
