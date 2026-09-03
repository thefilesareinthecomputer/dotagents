# Project Knowledge Vault - the contract

This folder is a **project knowledge vault**: one flat directory of markdown notes that the people and agents working a single project share as its operational source of truth. The project can be anything with a why and a body of work: a client delivery, a coding repo, a hobby build, a course of study. Everyone working it writes here. It replaces the hunt across chat threads, email, decks and half-current documents for the latest decision, process or state.

It has a second life. When the project ends the vault is cleaned up and kept, as the record of what was built and why, as the seed corpus for an agent that answers questions about it, or shipped with a deliverable as the knowledge wiki that goes to whoever takes it over.

Everything below is the contract. A skill or agent that reads a vault depends on **this contract**, never on a directory path.

## The one structural rule: flat

One directory. No subfolders. The **filename prefix** is the category, and the **filename sort order** is the abstraction ladder.

Link resolution, the knowledge-graph ingest and bulk upload all key on a single flat namespace, and a second folder reintroduces path fragility that filename resolution otherwise survives. The one exception is tooling state: a `vault-kg/` folder written by the knowledge-graph engine and any dot-folder are not notes and are not part of the vault.

## The ownership gradient

Sort order is also an ownership gradient, and knowing which end of it a file sits on tells you who edits it and how freely.

| Position | Files | Owner | How it changes |
|---|---|---|---|
| Top | `NN-*`, `agents-*` | Agent | Regenerated or appended by an agent; a human edits the source, not the output |
| Middle | `code-*`, `docs-*` | Ingested | Replaced wholesale when the upstream artifact changes; never hand-edited |
| Bottom | `notes-*`, `user-stories-*` | Human | Hand-written in the course of the work; an agent appends and refines but does not own |
| Reserved | `index.md`, `log.md` | Shared | Maintained by whoever adds or retires a note |

Collaboration happens across the gradient rather than in a designated place. The gradient tells you whose edit wins in a conflict: at the top the generator wins, at the bottom the human does.

## The file families

| Filename | `type:` | Holds |
|---|---|---|
| `NN-<slug>.md` | `reference` | The numbered navigation tier. Notes that map and interpret the corpus, sorted to the top. `00-brd` is the why. |
| `agents-<slug>.md` | `reference` | Agent-owned registers and logs: relay state, self-managed decision records, run history. Reserved family, seeded empty. |
| `code-<repo>[-<subsystem>].md` | `code` | Flattened repository contents, byte-identical. Never reformatted, never compressed. Re-flatten upstream to change one. |
| `docs-<origin>-<slug>.md` | `doc` | Ingested documents. `docs-internal-*` for material from the project's own people, `docs-research-*` for external. |
| `notes-chat.md` | `chat_log` | Message threads worth keeping, including email. One dated section per exchange. |
| `notes-meetings.md` | `meeting_note` | Standups, working sessions, refinements, planning. One dated section per meeting. |
| `notes-pr-reviews.md` | `note` | Story and pull-request reviews. One dated section per item under review, carrying its comment thread. |
| `notes-updates.md` | `note` | Status write-ups and per-topic summaries. One dated section per update. |
| `notes-learnings.md` | `note` | Durable facts written to outlive the threads that produced them. One dated section per sweep. |
| `notes-questions.md` | `note` | The open-question register. The only home for a question still awaiting an answer. |
| `user-stories.md` | `user_story` | The live board. |
| `user-stories-tasks.md` | `user_story` | The run sheet for in-flight stories, and the scratchpad the human and the agent hand work back and forth in. |
| `user-stories-completed.md` | `user_story` | Cold storage. Finished work graduates here with its body and shape intact. |
| `index.md` | reserved | The front door. OKF §8. |
| `log.md` | reserved | The change history. OKF §9. |

**One file per theme.** Resist splitting a family by audience or channel. Internal and external conversations share `notes-chat.md`, because sequence is what makes supersession readable and two files destroy it. Note the audience inside the dated section heading instead.

`code-*` and `docs-*` are created by dropping ingested content in, so this template seeds none. `agents-*` is declared and unseeded: add one when an agent actually needs a durable register, not before.

## The abstraction ladder

Filename order encodes the shape of the project, top to bottom:

1. `00-brd` - **the why.** Requirements, the aggregate everything sums to.
2. The rest of the `NN-*` navigation tier - the refined-for-use layer that maps the corpus.
3. `code-*`, `docs-*`, `notes-*` - the source corpus, what was captured.
4. `user-stories-*` - **the what-now.** The concrete assigned work.

Work filters **up**: a story is the ground-level unit, the BRD is what it all adds up to. Read top-down for the why, bottom-up for what is in flight.

## Frontmatter

Every note except `index.md` and `log.md` carries parseable YAML frontmatter with a non-empty `type`. That is the OKF conformance floor and it is the only hard requirement. `AGENTS.md` and `CLAUDE.md` are the contract, not notes, and carry none.

```yaml
---
type: reference
title: Ingestion Patterns
description: One line. This is what index.md quotes, so write it to be read there.
tags:
  - ingestion
status: stable
date-created: YYYY-MM-DD
last-modified: YYYY-MM-DD
---
```

- `type` - required, non-empty. Use the value in the family table.
- `title`, `description`, `tags` - recommended. `description` is a single line and is what `index.md` quotes.
- `status` - `draft`, `stable`, or `deprecated`.
- `date-created`, `last-modified` - ISO `YYYY-MM-DD`.
- `skills` - on `00-brd` only, a list of the skills the project requires. This is the demand signal: a knowledge base that tracks proven skills diffs against it to find what the project needs that nobody has yet.

Additional keys are allowed and consumers tolerate ones they do not recognize. Do not invent a key where an existing one fits, and do not use the `kg-` prefix, which the knowledge-graph engine reserves.

## Header grammar

One H1 per note, the title. Below it, one idea per heading, because the graph addresses **sections**, not files. A heading that covers three things cannot be cited for one of them.

**Dated capture** (`notes-*` other than the question register). Newest first. An optional `# YYYY-MONTH` H1 groups the months.

```markdown
## YYYY-MM-DD-EVENT-SCOPE

<what happened>

### DECISIONS
- YYYY-MM-DD - <what was settled> - supersedes YYYY-MM-DD <ref>, <why>

### ACTIONS
- [ ] <action> (owner: <ROLE>; opened YYYY-MM-DD)
```

Chronology is parsed from the heading, never inferred from position, so the date is mandatory and ISO. A proposal is not a decision; only settled things go under `### DECISIONS`. Every subsection is optional and a thin entry stays thin. Two undated H2s are allowed: `## PREP: <event>` for material prepared before an event, which the graph pins as current and undated, and a closing `## Related`.

`notes-learnings.md` is dated capture with one difference: each fact under a sweep is its own `###` heading, not a bullet. The graph addresses sections, and a fact that is a bullet can be neither cited nor superseded on its own without taking the whole sweep with it.

**Backlog** (`user-stories.md`, `user-stories-completed.md`). The `sprint-board` skill owns the shape: its anatomy reference is the specification, its scaffolder writes the structure and its linter checks it. An item keeps that shape when it graduates to the completed file, so the same linter reads both. `user-stories-tasks.md` is a run sheet, not a board, with its own fixed sections.

**Reference** (`NN-*`, `agents-*`). One H2 per idea, closing with `## Related`.

## Links and the graph

- Internal references are `[[wikilinks]]`. Markdown links are for external URLs.
- `index.md` is the exception: its listing uses markdown links, because OKF §8 defines it that way.
- A `[[note#Heading]]` anchor must resolve to a real heading in that note.
- `## Related` is the semantic edge block: `- [[target]] - why this edge exists`. Structural mentions stay inline.
- Filenames are lowercase-kebab and **stable**. A rename breaks every inbound link, so rename deliberately and repoint in the same commit.
- A link to a note that does not exist yet is written as a backtick code span, never a wikilink. Upgrade it when the target lands.

## Open questions have exactly one home

`notes-questions.md` is the only place an **open** question lives. One entry per question, carrying the date opened, the owner, the question, and a wikilink to where it arose. When it is answered, the answer and its date go on the entry and it moves to `## ANSWERED`.

Everywhere else, a question is a **closed record of what was asked on a date**, not a tracker. A `### QUESTIONS` bullet inside a dated section records that the question was raised then. A reference note carries no `## Open questions` section and links to the register instead.

## `index.md` and `log.md` follow OKF

Both are reserved filenames under [Google's Open Knowledge Format v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format). Neither is a concept document and neither takes frontmatter, with one exception: the bundle-root `index.md` may declare `okf_version`.

`index.md` lists the bundle's contents with a description each, grouped for progressive disclosure, using markdown links.

`log.md` is a flat chronological history, **newest first**, grouped under ISO `YYYY-MM-DD` H2s. One line per note added, removed, renamed or materially changed.

Because every other note already carries a non-empty `type`, this vault sits one step from full OKF bundle conformance. The remaining gap is link form: OKF specifies markdown links throughout, and this vault uses wikilinks so that Obsidian renders the graph. Convert the links at handoff if the receiving consumer requires conformance.

## Supersession, not deletion

A fact that stops being true is **superseded**, not erased. Write the new truth in a new dated entry and name what it replaces:

```markdown
- YYYY-MM-DD - <the new truth> - supersedes YYYY-MM-DD <ref>, <what changed>
```

The old entry stays where it is and gains one marker line, so the knowledge graph ranks it below the entry that replaced it:

```markdown
**SUPERSEDED**: YYYY-MM-DD <ref>
```

The marker closes the whole heading section it sits in, which is why a superseded thing must be its own section: a dated entry, or a single learning under its `###`.

Anyone reading the sequence can see what was believed when and why it changed, which is the whole reason the dated sections are ordered.

As a family grows past what is useful to read, compact the oldest entries: fold the settled ones into `notes-learnings.md` as durable facts, and leave the superseded chatter behind. Compact, never truncate.

## Nothing secret

A vault travels further than the people who wrote it, and its history keeps what a later cleanup removes. No credentials of any kind, no connection strings, no hostnames, workspace URLs, account or workspace ids, and no personal data. Where a real value is needed to make a note usable, name the place it is stored rather than the value.
