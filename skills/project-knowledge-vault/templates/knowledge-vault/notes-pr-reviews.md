---
type: reference
title: notes-pr-reviews
description: Story and pull-request reviews, each section carrying the item under review and its comment thread.
tags:
  - review
  - pull-request
coverage_start: YYYY-MM-DD
updated: YYYY-MM-DD
---

# PR-REVIEWS
[YYYY-MONTH](#YYYY-MONTH)

Newest first, one section per pull request. The value here is not the verdict but the reasoning: why a change was asked for, what it turned out to depend on, and what the reviewer found that the author had not. Draft comments live here in fenced blocks until they are posted.

> [!note] Entry format
> One H2 per pull request, `## PR-STORY-<id>-<INITIALS>-YYYY-MM-DD`, where the initials are the author's and the date is when the review opened. Each month opens with a `# YYYY-MONTH` H1 and gets a jump link at the top of the file. A review that settles a convention larger than the change records it under DECISIONS, and it moves to [[notes-learnings]] once it proves durable.

`````markdown
## PR-STORY-<id>-<INITIALS>-YYYY-MM-DD

**PR DESCRIPTION**
````
````

**PR FILES**
````
````

**PR COMMENTS**
````
````

**COMMENTS-DRAFT**
````
````

### DECISIONS
- YYYY-MM-DD - <what the review settled beyond this one change> - supersedes YYYY-MM-DD <ref>, <what changed>
`````

---
# YYYY-MONTH

---
