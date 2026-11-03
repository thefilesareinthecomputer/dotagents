---
type: reference
title: notes-learnings
description: Durable mechanical facts, one dated section per sweep, written to outlive the threads that produced them.
tags:
  - learnings
  - findings
  - mechanics
coverage_start: YYYY-MM-DD
updated: YYYY-MM-DD
---

# LEARNINGS
[YYYY-MONTH](#YYYY-MONTH)

## About this file

The temporal spine of the project. Everywhere else records what happened; this records what turned out to be **true**, in a form that still reads correctly a year after the thread that produced it is gone.

A learning earns a place here by being mechanical and checkable: how a system actually behaves, where a value is really set, what a process actually requires, which assumption was wrong. A status update is not a learning. Write the fact, not the story of finding it.

**This file connects four kinds of note.**

| Kind | Notes | What it contributes |
|---|---|---|
| Work items | [[user-stories]], [[user-runsheet]], [[user-stories-backlog]], [[user-stories-completed]] | What was asked for, what is being done about it, what closed |
| Narrative | the `notes-*` files: [[notes-meeting-notes]], [[notes-general-notes]], [[notes-email-notes]], [[notes-pr-reviews]], [[notes-updates]] | Where it was argued, decided or reviewed, and on what date |
| Documents | the `docs-*` files | What was written down at the time, and what has since gone stale |
| Code | the `code-*` files | What is actually true, which outranks every note |

**Every entry names as many of the four as apply**, with the dated heading or the section it points at. A story with no code link is a claim about intent; a code fact with no story link is a finding nobody owns.

**Wikilink the bare note name.** Only notes in this vault are link targets. Anything else, such as a deliverable that lives outside the vault, is written as a backtick code span.

> [!note] Entry format
> One H2 per sweep, `## YYYY-MM-DD - <one line saying what the sweep found>`, newest first. Under it, one H3 per fact, so each can be cited and superseded on its own, and an optional `### DECISIONS` closing the sweep. Each month opens with a `# YYYY-MONTH` H1 and gets a jump link at the top of the file.
>
> A fact that a later sweep supersedes stays put and gains one marker line under its heading, `**SUPERSEDED**: YYYY-MM-DD <ref>`, so the knowledge graph ranks it below its replacement. When a `notes-*` file grows past what is useful to read, fold its settled facts into a sweep here and leave the superseded chatter behind. Compact, never truncate.

```markdown
## YYYY-MM-DD - <what this sweep found, in one line>

### <the fact, stated flat>

<the mechanism or the evidence>. Found via [[notes-meeting-notes#YYYY-MM-DD-STANDUP]], confirmed in `code-<repo>`.

### <a corrected belief>

Supersedes YYYY-MM-DD <ref>: <what changed and how it was confirmed>.

### DECISIONS
- YYYY-MM-DD - <what was settled> - supersedes YYYY-MM-DD <ref>, <why>
```

---
# YYYY-MONTH

---
