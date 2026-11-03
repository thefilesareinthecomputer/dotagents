---
type: user_story
title: user-runsheet
description: Run sheet for the open stories. What to do, where, in what order, and what blocks what.
tags:
  - user-stories
  - run-sheet
updated: YYYY-MM-DD
---

# USER-RUNSHEET

One paragraph on what is in flight right now, naming each story on [[user-stories]] that this sheet covers.

Every step is executable: the command, the query, the file to open. A step that states an outcome rather than an action cannot be handed to anyone. A step is drained once it is done, and anything durable it produced goes to the note that owns it: a fact to [[notes-learnings]], a decision to the dated section where it landed, an open question to [[notes-questions]]. Nothing is archived from here.

# START HERE

The one ordered list to work from, across every story, in execution order. A step that hands work to a coding assistant holds the paste-in block inside the step, so the step and its instructions never drift apart.

## Now: <the next thing to do>

Where things stand, YYYY-MM-DD:
- <the state a reader needs before step 1>

1. [ ] <the action> - `<the command or the path>`
2. [ ] <the action>, blocked by 1
3. [ ] <the action>, blocked by <ROLE> granting <what>

## STORY-<id>

Steps for one story that sit outside the START HERE order, grouped by phase.

### <phase>

1. [ ] <the action> - `<the command or the path>`

# FOR THE AGENTS

Standing context each coding assistant or agent needs before it touches this project's work: which repository, which tool is the fallback, and where its current brief is. One H3 per assistant.

### <assistant> in <where it runs>

<where its brief is, and what it must not do>
