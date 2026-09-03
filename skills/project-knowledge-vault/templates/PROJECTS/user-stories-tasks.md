---
type: user_story
title: user-stories-tasks
description: The run sheet for in-flight stories, and the scratchpad the team and its agents hand work back and forth in.
tags:
  - user-stories
  - run-sheet
status: stable
date-created: YYYY-MM-DD
last-modified: YYYY-MM-DD
---

# USER-STORIES-TASKS

The working surface for whatever is in flight on [[user-stories]]. Two things live here because they are the same conversation: the ordered run sheet, and the scratchpad where a question is handed over and an answer comes back.

Both halves are temporary. A line is drained once it is done, and anything durable that came out of it is written to the note that owns it - a fact to [[notes-learnings]], a decision to the dated section where it landed, an open question to [[notes-questions]]. Nothing is archived from here.

## RUN SHEET

What to do, where, in what order, and what blocks what. Every line is executable: the command, the query, the file to open. A line that states an outcome rather than an action cannot be handed to anyone.

### STORY-<id> - <short title>

- [ ] 1. <the action> - `<the command or the path>`
- [ ] 2. <the action>, blocked by 1
- [ ] 3. <the action>, blocked by <ROLE> granting <what>

## SCRATCHPAD

Dated blocks, newest first. Post one when handing work over, and reply in place under it.

### YYYY-MM-DD - <ROLE or agent> - <what is being handed over>

<the question or the handover, with everything needed to act on it>

**Reply** YYYY-MM-DD - <the answer>

## AWAITING A REPLY

- <what was asked>, of <ROLE>, since YYYY-MM-DD - Q-<id> in [[notes-questions]]

<!--
An item that has been awaiting a reply long enough to matter is no longer a scratchpad note.
Open it in notes-questions.md with an owner, and leave a link here.
-->
