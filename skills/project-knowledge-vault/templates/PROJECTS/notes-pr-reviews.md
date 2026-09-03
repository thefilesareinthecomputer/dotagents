---
type: note
title: notes-pr-reviews
description: Story and pull-request reviews, each dated section carrying the item under review and its comment thread.
tags:
  - review
  - pull-request
status: stable
date-created: YYYY-MM-DD
last-modified: YYYY-MM-DD
---

# PR-REVIEWS

Newest first, one H2 per item reviewed. The value here is not the verdict but the reasoning: why a change was asked for, what it turned out to depend on, and what the reviewer found that the author had not.

## YYYY-MM-DD-PR-<id>-<short-slug>

- **Item** <PR or story reference> - **Author** <ROLE> - **Reviewer** <ROLE>
- **Outcome** approved / changes requested / closed

<what the change does, in one or two sentences>

### COMMENTS

- **<file or area>** - <what was raised, and what was agreed>

### DECISIONS

- YYYY-MM-DD - <what the review settled beyond this one change> - supersedes YYYY-MM-DD <ref>, <what changed>

### ACTIONS

- [ ] <follow-up the review left behind> (owner: <ROLE>; opened YYYY-MM-DD)

<!--
A review that establishes a convention has settled something larger than the pull request.
Record that under DECISIONS so it is findable by someone who was not on the thread, and fold it
into notes-learnings.md when it proves durable.
-->
