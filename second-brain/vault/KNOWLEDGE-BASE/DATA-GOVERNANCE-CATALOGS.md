---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - governance
  - catalog
---

# Governance Catalogs

The catalog is the control plane of a
[[DATA-MEDALLION-ARCHITECTURE-OVERVIEW|lakehouse]]: one place that knows
what exists, who may touch it, and where it came from. Unity Catalog plays
this role on Databricks; Purview plus the workspace/OneLake security model
plays it on [[DATA-LAKEHOUSE-PLATFORMS|Microsoft Fabric]].

## What a catalog owns

- **Namespace** - catalog.schema.table addressing that outlives any single
  engine or workspace.
- **Access control** - grants on securables, row filters and column masks;
  strictest where audiences are widest ([[DATA-GOLD-LAYER|gold]]).
- **Lineage** - column-level traces across the bronze-silver-gold hops;
  the debugging path when a number looks wrong, and the blast-radius map
  when a [[DATA-SILVER-LAYER|silver]] contract must change.
- **Discovery** - descriptions, tags, and certification marks so consumers
  find the blessed table instead of a lookalike.
- **Audit** - who read what, when; the compliance answer that object
  storage alone cannot give.

## Working rules

- Grants go to groups, never individuals; ownership is a role, not a
  person.
- Sensitive columns get masked at the catalog so every engine inherits the
  policy - masking in each dashboard is a whack-a-mole loss.
- External locations and [[DATA-INGESTION-PATTERNS|landing zones]] register
  in the catalog too; ungoverned paths are where shadow copies breed.
- Certification marks on [[DATA-GOLD-LAYER|gold]] tables are earned by
  passing [[DATA-QUALITY-EXPECTATIONS|expectations]], not self-declared.
