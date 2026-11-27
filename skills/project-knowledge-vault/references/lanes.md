# Lanes - where project knowledge lives

This is the one statement of the model.
Skills that read or write `docs/`, `tasks/` or `kb/` link here and do not restate it.

## Contents

- The three lanes
- Where things go
- Graduation
- Link direction
- Workspaces of several projects
- Graphs
- Reading a query result
- Legacy layouts

## The three lanes

| Lane | Holds | Written by | Tracked in git |
|---|---|---|---|
| `docs/` | Graduated, verified knowledge: `SPEC.md`, `ARCHITECTURE.md`, `adr/`, `designs/`, `research/` | the agent, once the content is real | yes |
| `tasks/` | The agent's queue: `plan.md`, `todo.md`, in-progress `SPEC-<NAME>.md`, `backlog/`, `completed/`, and records such as `boards/`, `reviews/` and `supervisor/` | the agent | usually not (see below) |
| `kb/` | The project's working vault: the user's run sheet, `notes-*` logs, `user-stories*` notes, learnings, questions | the user, and agents through the skills below or when the user asks | not by default; yes in a private team repo |

- `README.md`, `AGENTS.md`, `CHANGELOG.md` and `LICENSE` stay at the repo root, where tools and hosts look for them.
- `tasks/` is gitignored when the repo itself is public.
  Whether `kb/` is tracked is the repo's `.gitignore`'s call; the vault scaffolder does not edit it.
- **What the link check treats as not committed** comes from git: anything untracked or gitignored.
  A normal repo needs nothing more. A private repo that tracks folders it never publishes
  (it publishes a filtered public copy) lists them under `holdback` in `docs/.kg/markdown-kg-config.json`,
  anchored at the root, such as `["/tasks/", "/_RESEARCH/"]`, so the check treats them as not committed too.
  When the repo gitignores `.kg/`, that config is per station: keep the list with the repo's own publishing notes
  and set it again on each station and after a rebuild.
- `kb/` is a flat project vault seeded by `project-knowledge-vault`.
  Its own `AGENTS.md` is the vault contract: every note role, its format and its writer.

Skills that write `kb/` notes, each within the contract:

- `sprint-board` defines the format of `user-stories.md` and `user-stories-completed.md`.
  The agent edits those two when the user asks or when `sprint-board` runs.
- `gather-learnings` sweeps into `notes-learnings.md`, `notes-questions.md` and `notes-updates.md`, and drains finished steps from the run sheet.
- `get-ready` writes steps and briefs into the run sheet, `user-runsheet.md`.
- `compact-notes` rewrites meeting-note sections in place.

All four `user-stories*` notes (`user-stories.md`, `-backlog`, `-completed`, `-research`) stay together in `kb/`.
The backlog and research notes are the vault's own working files, edited by any agent on request.
A story picked up for work gets a `tasks/` item that points back at it.

## Where things go

| Content | Goes to |
|---|---|
| A feature spec being built | `tasks/SPEC-<NAME>.md` |
| A written spec nobody is building yet | `tasks/backlog/` |
| The current workstream and the session handoff | `plan.md` and `todo.md` in `tasks/` |
| The plan of record for a large initiative the agent runs | `tasks/boards/<initiative>.md`, in `sprint-board`'s format |
| Shipped records and retired specs | `tasks/completed/` |
| What the system is: invariants, boundaries, constraining decisions | `docs/SPEC.md` (a repo that has not moved keeps it at the root) |
| How the parts fit together, when `SPEC.md` outgrows it | `docs/ARCHITECTURE.md` |
| A decision with the options that were weighed | `docs/adr/NNNN-title.md` |
| A solution design for a feature | `docs/designs/` |
| A guide or runbook the repo ships | `docs/` |
| Research verified and worth keeping | `docs/research/` |
| The project's stories as the user sees them | the `user-stories*` notes in `kb/` |
| The user's steps for the work in flight | `kb/user-runsheet.md` |
| Meetings, chat, email, status updates | the matching `kb/notes-*` note |
| A durable fact learned during the work | `kb/notes-learnings.md` through `gather-learnings`, then `docs/` once graduated |
| An open question | `kb/notes-questions.md` |
| Any other vault role (received documents, code dumps, `index.md`, `log.md`, the BRD) | where the vault contract in `kb/AGENTS.md` says |

The agent's own queue stays in `tasks/`; the run sheet holds the steps for the work in flight, as the vault contract describes.
When the repo has a `SPEC.md` (in `docs/` or at the root), it covers what a vault's BRD and north star would, so the vault does not seed those two.

## Graduation

Content moves one way, into `docs/`, and only once it is real.
Real means built and signed off by the user ("accepted" in an ADR means the same), or verified and approved by the user.

- **Agent work.** A `tasks/SPEC-<NAME>.md` is built and signed off, then moves to `tasks/completed/`.
  Its durable facts graduate into `docs/`: what the system now is becomes a `SPEC.md` section,
  and a choice between options becomes an ADR.
- **The user's knowledge.** A verified `kb/` learning graduates into `docs/` when the user approves,
  usually as a `SPEC.md` section. The `kb/` entry stays and gains the new file's path in backticks.
- **ADRs and designs** live in `docs/` from their first draft. Their status line (Proposed, Accepted) says whether they are real yet.
- **Who writes it.** `notes` and `wrap-up` propose graduations and write into `docs/` only on the user's yes.
  The one exception is correcting a claim that the session itself made false.

Nothing moves back out of `docs/`. A graduated fact that turns out wrong is corrected in place.

## Link direction

Links point toward `docs/`, never away from it.

| From | May cite |
|---|---|
| `docs/` | `docs/` and other committed files (code, skills, configs) |
| `tasks/` | `docs/`, `tasks/`, `kb/` and code |
| `kb/` | `docs/`, `kb/` and code; `tasks/` only while the note is not committed |

- A committed file never links to, or names by path, a specific uncommitted file.
  A link like that is dead for everyone who clones the repo.
  So a committed `kb/` note (in a team repo) follows the `docs/` rule and cannot cite a `tasks/` file.
- Naming a lane as a folder is fine: "agent working state lives in `tasks/`".
  A code span that names a folder is never checked.
- A `kb/` note cites a file outside the vault by its repo-relative path in backticks, such as `docs/adr/0003-cache.md`,
  as the vault contract says. Wikilinks stay for notes inside the vault.
- markdown-kg checks links and backticked file paths (see link statuses below).
  A bare path in plain prose cannot be checked, so that part of the rule is the agent's to keep.
- When `docs/` needs something that lives in `kb/` or `tasks/`, graduate it first, then cite the new `docs/` file.

## Workspaces of several projects

A workspace keeps each project's vault in `PROJECTS/<NAME>/`, beside a knowledge engine that queries across them.
There the vault is the project's working lane, and a `PROJECTS/<NAME>-DELIVERABLES/` sibling stands in for `docs/`:
it holds the ADRs, designs, guides and runbooks the project ships, and has its own graph, found like any project folder.
A vault inside a repo has no deliverables sibling; its ADRs and designs go to the repo's `docs/`.

## Graphs

- **markdown-kg keeps one graph per lane or project vault:** `docs/.kg/`, `kb/.kg/`, `PROJECTS/<NAME>/.kg/`.
  Lanes are never merged into one index; queries join them at read time.
- **`tasks/` has no graph, and no graph query ever covers it.**
  Read its files directly, or search them with `grep`. `hi` reads the hot files at session start;
  `backlog/` and `completed/` are read only when needed.
- **code-kg keeps one graph per repo,** in `.kg/` at the repo root.
- **A label names a graph:** its folder's path from the workspace root, such as `docs`, `kb` or `PROJECTS/ALPHA`.
  The workspace root is the first folder, walking up, that holds `PROJECTS/` or `.git`, else the home folder, never above it.
- **`markdown-kg graphs <path>` lists every graph around a path** with its label and ingest time.
  It also lists lanes that hold notes but have no graph, and a legacy `docs/kb/` graph.
- **A lane with notes and no graph** gets one with `markdown-kg init <folder>` followed by `markdown-kg ingest <folder>`.
  For `kb/`, the vault scaffolder does both.

## Reading a query result

A **scoped miss** is a query that found nothing in the graphs it searched.
It says nothing about the graphs it did not search, and nothing about `tasks/`.

- **`search`, `query`, `links`, `backlinks`, `refs` and `stats` print their scope first,** and so does code-kg's `docs`:
  which graph they searched and when it was last ingested, which graphs they did not search,
  and which lanes hold notes but have no graph.
  With `--json` the scope goes to stderr as one JSON line, and stdout is unchanged.
- **A zero-result answer from `search`, `query`, `links`, `backlinks` or `refs` ends with the widen command:** `This covers only <labels>. To widen: <command>`, or `This covers only <labels>; no other graph was found.` when there is nothing left to search.
  For `search`, `backlinks` and `refs` that is the same command with `--all`; for `query` and `links`
  it is the same command on each other graph; for a lane with no graph it is the `init` and `ingest` that index it.
  Run it before concluding that something does not exist.
- **`search --all`** searches every graph and labels each hit `[<label>]`.
  `read <vault> <section-id> --graph <label>` opens a hit from another graph.
- **An unresolved bare `[[Name]]`** may exist in a sibling graph; `search --all` can say.

A link to a file, as opposed to a wikilink to a note, gets one status, computed each time a command reads it.
The first row that matches wins:

| Order | Status | Meaning | What to do |
|---|---|---|---|
| 1 | `unresolved` | the target does not exist on disk | the only broken status: fix or remove the link |
| 2 | `forbidden` | a committed file points at a file in this repo that is not committed | graduate the target into `docs/` and repoint, or drop the link |
| 3 | `external` | the target exists outside this graph's folder, including outside the repo | nothing; normal for a `kb/` note citing `docs/` |
| 4 | `resolved` | the target exists inside this graph's folder | nothing |

- **Committed** means listed by `git ls-files` and not under a `holdback` glob. A source that is not committed never yields `forbidden`.
  `holdback` is set per graph, in that graph's markdown-kg config.
- **A backticked path** counts when it resolves to a file, against the repo root first and then the note's folder.
  One that resolves to nothing is ordinary text, never `unresolved`, so a note can name a file that does not exist yet.
- Wikilinks between notes keep their own statuses (`resolved`, `unresolved`, `ambiguous`, `ignored`).
- `links --forbidden` lists the forbidden links and exits 3 when there are any; outside git it says the check did not run.
  In a repo with a `docs/` graph, the commit hook runs it on `docs/` and blocks the commit until they are fixed.
  A committed `kb/` (a team repo) is checked by running `links --forbidden` on `kb/` by hand.

## Legacy layouts

- **A vault at `docs/kb/`** moves to `kb/`, with `git mv` when it is tracked, then `kb/` is ingested.
  `markdown-kg graphs` lists such a graph as `legacy` and prints that instruction.
- **A root `SPEC.md`** still works: skills look for `docs/SPEC.md` first, then the root.
  Move it when the repo is next worked on.
