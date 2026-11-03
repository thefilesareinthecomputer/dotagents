---
type: user_story
title: user-stories
description: The live board. Epics, features and stories in execution order; finished work graduates to user-stories-completed.
tags:
  - user-stories
  - backlog
updated: YYYY-MM-DD
---

# USER-STORIES

The live board for this project, and the bottom rung of the ladder: every item here rolls up to something stated in [[00-brd]]. Work that is not on the board yet sits in [[user-stories-backlog]], the steps for work in flight are in [[user-runsheet]], and finished items move to [[user-stories-completed]] rather than being deleted.

**The `sprint-board` skill owns this file's structure.** Its `references/anatomy.md` is the specification for the heading hierarchy, the parent declaration and the epic, feature and story bodies; its `board_lint.py` is the check. Neither is restated here, so that there is only ever one copy to keep current.

> [!note] Starting the board
> The board starts empty. Write the spine as JSON and run sprint-board's `board_scaffold.py` to generate the items, appended below AGENT-NOTES; never hand-type a block. Run `board_lint.py` before handing the board to anyone.

## AGENT-NOTES

Standing context an agent needs before touching the board: which external system this mirrors, which IDs are authoritative, and what must never be edited here. Keep it short enough to be read every time.
