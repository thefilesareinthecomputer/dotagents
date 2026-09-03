---
type: user_story
title: user-stories
description: The live board. Epics, features and stories in execution order; finished work graduates to user-stories-completed.
tags:
  - user-stories
  - backlog
status: stable
date-created: YYYY-MM-DD
last-modified: YYYY-MM-DD
---

# USER-STORIES

The live board for this project, and the bottom rung of the ladder: every item here rolls up to something stated in [[00-brd]].

**The `sprint-board` skill owns this file's structure.** Its `references/anatomy.md` is the specification for the heading hierarchy, the parent declaration and the epic, feature and story bodies; its `board_lint.py` is the check. Neither is restated here, so that there is only ever one copy to keep current.

## AGENT-NOTES

Standing context an agent needs before touching the board: which external system this mirrors, which IDs are authoritative, and what must never be edited here. Keep it short enough to be read every time.

<!--
The board starts empty. Write the spine as JSON and run sprint-board's board_scaffold.py to
generate the items below this comment; never hand-type a block. Run board_lint.py before
handing the board to anyone.

Work in flight has a run sheet in user-stories-tasks.md. Finished items move to
user-stories-completed.md rather than being deleted, so the board stays the live picture.
-->
