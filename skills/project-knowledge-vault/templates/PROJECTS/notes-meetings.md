---
type: meeting_note
title: notes-meetings
description: Standups, working sessions, refinements and planning, one dated section per meeting.
tags:
  - meeting
  - standup
status: stable
date-created: YYYY-MM-DD
last-modified: YYYY-MM-DD
---

# MEETING-NOTES

Newest first. One H2 per meeting, `## YYYY-MM-DD-EVENT-SCOPE`, where scope names the audience so that an internal session and an external one are distinguishable without opening them. Optional `# YYYY-MONTH` H1s group the months once the file gets long.

## YYYY-MM-DD-STANDUP-INTERNAL

What was covered, in enough detail that someone who missed it does not have to ask. Attribute by role or initials rather than by full name.

### DECISIONS

- YYYY-MM-DD - <what was settled, and what it commits us to> - supersedes YYYY-MM-DD <ref>, <what changed>

### QUESTIONS

- <what was raised and left unanswered>

### ACTIONS

- [ ] <action> (owner: <ROLE>; opened YYYY-MM-DD)

<!--
Every subsection is optional. A thin meeting stays thin.

A proposal is not a decision. Only settled things go under DECISIONS, and a decision that
replaces an earlier one names it, so the sequence reads as a history rather than a pile.

A QUESTIONS bullet records that the question was raised on this date. It does not track it.
Anything still open also gets an entry in notes-questions.md, which is the only place an open
question is tracked.
-->
