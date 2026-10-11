---
date-created: 2026-08-26
last-modified: 2026-08-26
status: template
tags:
  - project
  - docs
---

# Docs: Data Model

A `docs-*` note distilling the project's core entities from raw sources into linkable form. Placeholder content demonstrating the shape.

## Entities

| Entity | Key fields | Notes |
|---|---|---|
| Record | id, created_at, status | one row per source item |
| Batch | id, run_date, record_count | groups records per run |
| Outcome | record_id, verdict, reviewed_by | one per processed record |

## Relationships

A Batch has many Records; each Record has exactly one Outcome. Contradictions between a raw source and this model get logged in [[PROJECTS/PROJECT-A/notes-learnings|notes-learnings]] and resolved here, per [[docs-architecture]]'s decisions.
