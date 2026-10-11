---
date-created: 2026-08-26
last-modified: 2026-08-26
status: template
tags:
  - project
  - docs
---

# Docs: Architecture

A `docs-*` note holds a design or reference document the project produced or depends on. Long source documents that arrive as PDFs or exports go in `raw/`; this note distills them into linkable markdown.

## Shape

```mermaid
flowchart LR
  A[Source data] --> B[Transform]
  B --> C[Store]
  C --> D[Consumers]
```

## Decisions

- One decision per bullet, with its one-line why, so [[PROJECTS/PROJECT-A/user-stories-backlog|user-stories-backlog]] items can cite them.
