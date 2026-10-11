---
date-created: 2026-08-26
last-modified: 2026-08-26
status: canonical
tags:
  - vault
  - lifecycle
  - meta
---

# The Knowledge Lifecycle

A vault in this tiered layout can run a closed loop, where knowledge is earned rather than collected and every note in `KNOWLEDGE-BASE/` passed through the same gate. The loop is run by skills that live with the vault that uses them, not by this app; the sample vault here follows the layout and this note describes the loop those skills implement.

## The loop

1. **Research** stages findings in `_RESEARCH/` as dated artifacts with sourced claims and confidence ratings. Example: [[2026-08-26-second-brain-knowledge-graph-landscape]].
2. **Certification** tests the owner on the artifact: a written open-book exam (pass at 90 percent or above), then an inline Socratic and Feynman teach-back. Certs live in `LEARNING/` and share the artifact's date-slug stem, like [[2026-08-26-second-brain-knowledge-graph-landscape-cert]].
3. **Merge** promotes certified material into `KNOWLEDGE-BASE/` through the merge gate. The gate refuses `pending-review` artifacts and sub-90 certs. No partial merges.
4. **Projects** in `PROJECTS/` consume the knowledge base. See the template workspace at [[PROJECTS/PROJECT-A/index|PROJECT-A]].
5. **Gap assessment** scores a project's required knowledge against `KNOWLEDGE-BASE/` only. It is blind to `_RESEARCH/` by design. The ranked gap queue becomes the next research work order, closing the loop.

Validated mastery accumulates in the owner's ledger under `_USER/`, which is per user and not part of the sample vault.

## Invariants

- Content enters `KNOWLEDGE-BASE/` only through the merge gate. Never directly.
- `_RESEARCH/` never counts as knowledge.
- Certification is two-stage and all-or-nothing.
- A research artifact, its certification, and its study materials share one `YYYY-MM-DD-slug` stem.
- Nothing is deleted. Superseded material moves to `__archive/`.
