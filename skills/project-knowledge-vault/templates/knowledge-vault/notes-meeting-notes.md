---
type: meeting_note
title: notes-meeting-notes
description: Standups, working sessions, refinements and planning, one dated section per meeting.
tags:
  - meeting
  - standup
  - working-session
coverage_start: YYYY-MM-DD
updated: YYYY-MM-DD
---

# MEETING-NOTES
[UPCOMING](#UPCOMING)
[YYYY-MONTH](#YYYY-MONTH)

Newest first, one section per meeting, in enough detail that someone who missed it does not have to ask. Attribute by role or initials rather than by full name.

> [!note] Entry format
> One H2 per meeting, `## YYYY-MM-DD-<EVENT>`, where the event names the meeting (`STANDUP`, `REFINEMENT`) or the participants' initials for a working session. Each month opens with a `# YYYY-MONTH` H1 and gets a jump link at the top of the file. Every subsection is optional, and a thin meeting stays thin.
>
> A proposal is not a decision. Only settled things go under DECISIONS. A QUESTIONS bullet records that a question was raised on that date and does not track it; a question still open also goes in [[notes-questions]].

```markdown
## YYYY-MM-DD-STANDUP

<what was covered>

### DECISIONS
- YYYY-MM-DD - <what was settled, and what it commits us to> - supersedes YYYY-MM-DD <ref>, <what changed>

### QUESTIONS
- <what was raised and left unanswered>

### ACTIONS
- [ ] <action> (owner: <ROLE>; opened YYYY-MM-DD)
```

---
# UPCOMING

Prep for things that have not happened yet. Not a record. Each block is a `## PREP: <event>` section, which the knowledge graph keeps current and undated, and it moves down into the dated history once the meeting happens.

---
# YYYY-MONTH

---
