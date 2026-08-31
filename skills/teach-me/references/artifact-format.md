# LEARNING/ artifact formats

All artifacts live in `LEARNING/` at the root of the workspace where the skill
is called (created on first use; writing anywhere else is ask-first). One topic
file per topic; one additional dated file per re-cert.

The workspace root is `git rev-parse --show-toplevel` when inside a repo,
otherwise the current working directory. If the resolved root is `$HOME` or a
synced tooling repo (`~/.agents`, `~/.claude`), stop and confirm the
destination with the user before writing - personal learning artifacts do not
belong in shared source-of-truth repos by default.

## Topic file - `LEARNING/<topic-slug>.md`

Created by the first session (either mode). Status lifecycle: `guide` (written
study guide, uncerted) upgrades to `certified` when the inline cert is passed.
Direct mode with no guide requested skips guide content and the file is the
cert record.

```markdown
---
topic: CRDTs - conflict-free replicated data types
source: tasks/research-crdts-2026-07-28.md
created: 2026-07-28
last-cert: 2026-07-28
score: 4/5
status: certified
---

# CRDTs - certified 4/5 (2026-07-28)

## Study guide            <- guide-first mode only
[distilled teachable content, structured by concept]

## Cert record - 2026-07-28
Predicted score: 3/5 · Actual: 4/5

1. Q: [question]
   A (learner): [tracked answer]
   Verdict: correct | partial | wrong - [one-line feedback given]
...

## Gaps and closures
- [gap revealed in EXPLAIN/PROBE] - closed by [what closed it]

## Re-test pack
For future on-demand re-certs; do not show before attempts.
- [question] (tests: [concept]) - answer: [terse answer]
- [transfer question seed: vary surface, keep deep structure]
```

## Re-cert file - `LEARNING/<topic-slug>-cert-YYYY-MM-DD.md`

Each later re-cert is a new dated file. An explicit retake of a specific cert
updates that cert's file (attempt history appended), never a new file. Either
way, update the topic file's `last-cert` and `score` frontmatter.

```markdown
---
topic: CRDTs - conflict-free replicated data types
topic-file: crdts.md
cert-date: 2026-08-15
score: 3/5
attempts: 1
---

# CRDTs re-cert - 3/5 (2026-08-15)

Predicted score: 4/5 · Actual: 3/5

[questions + tracked answers + verdicts, as in the topic file's cert record]

## Weak spots this round
- [item] - queued for next re-cert
```

## Rules

- Scores are `correct/total`; partial credit counts as 0.5 and is called out.
- The H1 always carries the latest score and date for scan-at-a-glance.
- Practice-cert questions (guide-first mode) never reappear as final-cert
  questions; re-test packs may reuse cert items plus fresh transfer variants.
- Frontmatter keys are lowercase kebab-case; dates are YYYY-MM-DD.
- The topic slug is short kebab-case from the topic name, stable across
  sessions - characters `[a-z0-9-]` only, no dots or path separators; the
  write path never escapes `LEARNING/`.
- Upgrading a guide or recording a retake rewrites an existing file: read it
  first and preserve prior cert records and attempt history.
