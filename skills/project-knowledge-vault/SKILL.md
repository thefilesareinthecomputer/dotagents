---
name: project-knowledge-vault
description: >-
  Seeds and checks a project knowledge vault - one flat folder of markdown
  notes that the people and agents on a project share as its operational
  source of truth, OKF-compatible and readable by obsidian-kg as its own
  graph. Owns the contract (AGENTS.md), the seed files, a scaffolder and a
  conformance linter. Use when starting a project vault or a new project under
  PROJECTS/, when asked to set up, seed, scaffold or template a project's
  notes, when checking whether a vault conforms or why the graph or the board
  tools read it badly, or when a project needs a home for its meetings, chat,
  learnings, questions and user stories. Works for any project in any domain.
  The knowledge base, learning path and research flows around it belong to
  their own skills; so do the board (sprint-board) and the graph (obsidian-kg).
---

# project-knowledge-vault

A project vault is the hub object of a knowledge stack. It is one flat directory, and the filename prefix is the category: `00-brd` states the why, `notes-*` capture what happened, `notes-learnings` holds what turned out to be true, `notes-questions` is the one register of open questions, and `user-stories*` hold the work. `index.md` and `log.md` are the OKF front door and change history. The full contract is `templates/PROJECTS/AGENTS.md`, and that file ships into every vault, so the contract has exactly one copy.

## Commands

```
seed      python3 scripts/vault_scaffold.py --target <path> --name <NAME> [--dry-run]
lint      python3 scripts/vault_lint.py <path>/PROJECTS/<NAME> [--json]
test      python3 -m pytest tests -q
```

The scaffolder writes `<path>/PROJECTS/<NAME>/` from `templates/PROJECTS/`. It never overwrites: an existing file is reported as skipped, so a run against a part-built vault fills the gaps. It resolves no dates, so two runs on different days are byte-identical. Exit 1 means a file could be neither written nor skipped.

The linter is the anti-drift mechanism. Every check fires on positive evidence, and an unreadable file is a failure rather than a pass. Exit 0 clean, 1 on any finding.

| check | fails on |
|---|---|
| `flat` | any subdirectory other than `vault-kg/` or a dot-folder |
| `frontmatter` | a note without parseable YAML carrying a non-empty `type` |
| `family` | a `type` outside the family table for that prefix, or a prefix in no family |
| `reserved` | `index.md` or `log.md` missing, or frontmatter beyond `okf_version` on the root index |
| `filename` | anything not lowercase-kebab |
| `wikilink` | a `[[target]]` with no note in the vault |
| `anchor` | a `[[note#Heading]]` whose heading does not exist |
| `dated` | a `notes-*` H2 that is not `YYYY-MM-DD-...`, `PREP: ...` or `Related`; `log.md` H2s not ISO and newest first |
| `board` | `user-stories.md` restating sprint-board's grammar instead of pointing at it |
| `placeholder` | a literal `YYYY-MM-DD` in a hand-written note that already carries real dates |

`AGENTS.md` and `CLAUDE.md` are the contract, not notes. `code-*` and `docs-*` are ingested byte-for-byte and are exempt from the placeholder check. `notes-questions.md` is a register with `OPEN` and `ANSWERED` sections, not dated capture.

## Where it sits in the stack

- **obsidian-kg** reads each project vault as its own graph root: `obsidian_kg.py init <path>/PROJECTS/<NAME>`, then merge the rows in `templates/vault-kg-profiles.md` into the config it wrote. Every project vault carries the same reserved filenames, so a graph over all of `PROJECTS/` would find every bare wikilink ambiguous; a parent vault's own graph ignores `PROJECTS/**` in its `.kgignore`. The engine's `index` command writes `Vault Index.md` and never `index.md`. Supersession uses the engine's `**SUPERSEDED**: <ref>` marker, which closes the heading section it sits in, which is why each learning is its own `###`.
- **sprint-board** owns `user-stories.md` and `user-stories-completed.md`. The seed ships the board empty; write the spine as JSON, run its `board_scaffold.py`, and append the output after the seed's preamble. A fresh scaffold reports template residue until the bodies are written, and that is the author's job, not the vault's.
- **The knowledge base, learning path and certification flow** live outside the vault. A project pushes durable facts up through `notes-learnings.md` for the certification flow to promote, and declares what it needs in the `skills:` list on `00-brd.md`, which a knowledge base diffs against its proven skills to find the gap and seed the learning path.
- **okf-vault** (a build pipeline in another repo) produces a vault of this shape from raw sources. The relationship is a conformance check, not a dependency: point `OKF_VAULT_BUILD` at a build output and the test suite lints it.

## Boundaries

**Always** lint a vault before calling a change to it done. Repoint every inbound link in the same commit as a rename. Keep the contract to one copy.

**Ask first** before adding a second template profile, changing a family name or `type` value (every existing vault stops conforming), or resolving a real date into a template file.

**Never** teach obsidian-kg the contract, restate sprint-board's anatomy in the seed, use a `kg-` frontmatter key, or put an identifier in anything under `templates/`. The templates ship into public repos and git history keeps what a later cleanup removes.

## Files

- `templates/PROJECTS/` - the 14 seed files, including the contract
- `templates/vault-kg-profiles.md` - config rows for obsidian-kg
- `scripts/vault_scaffold.py`, `scripts/vault_lint.py`
- `tests/` - scaffold, one adversarial fixture per linter check, and the compatibility tests against sprint-board and obsidian-kg
