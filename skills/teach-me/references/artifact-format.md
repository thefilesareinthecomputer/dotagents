# Session record formats

Every session ends with its record given in the chat. The skill keeps no folder of its own: a record is saved to a file only when the user asks, at the path the user names, and a later re-cert reads one only when the user pastes it in or points at it.

## Topic record

Given at the end of the first session on a topic (either mode). Status is `guide` for a study guide with no cert yet, and `certified` once the inline cert is passed. In direct mode with no guide requested, the record has no study guide section.

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

## Re-cert record

Each later re-cert gets its own dated record. Where the user saved the topic record, the re-cert also gives its new `last-cert` and `score` for it.

```markdown
---
topic: CRDTs - conflict-free replicated data types
cert-date: 2026-08-15
score: 3/5
attempts: 1
---

# CRDTs re-cert - 3/5 (2026-08-15)

Predicted score: 4/5 · Actual: 3/5

[questions + tracked answers + verdicts, as in the topic record's cert record]

## Weak spots this round
- [item] - queued for next re-cert
```

## Rules

- Scores are `correct/total`; partial credit counts as 0.5 and is called out.
- The H1 always carries the latest score and date for scan-at-a-glance.
- Practice-cert questions (guide-first mode) never reappear as final-cert
  questions; re-test packs may reuse cert items plus fresh transfer variants.
- Frontmatter keys are lowercase kebab-case; dates are YYYY-MM-DD.
- Updating a saved record means reading it first and keeping its prior cert
  records and attempt history.
