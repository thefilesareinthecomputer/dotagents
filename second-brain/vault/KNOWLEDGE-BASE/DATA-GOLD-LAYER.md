---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - medallion
  - gold
---

# Gold Layer

Gold is the consumption tier of the
[[DATA-MEDALLION-ARCHITECTURE-OVERVIEW|medallion architecture]]: data shaped
for the people and systems that use it, built from
[[DATA-SILVER-LAYER|silver]]'s conformed entities.

## Typical gold shapes

- **Dimensional models.** Facts and dimensions for BI - the star schema is
  alive and well in the lakehouse; it just materializes as
  [[DATA-DELTA-LAKE-FORMAT|Delta]] tables now.
- **Wide denormalized marts.** One-big-table serving a specific dashboard
  or export, traded consciously against reuse.
- **Feature tables.** Point-in-time correct inputs for ML training and
  serving.
- **Aggregates and semantic layers.** Pre-computed rollups, or metric
  definitions pushed into the platform's semantic model (Power BI on
  [[DATA-LAKEHOUSE-PLATFORMS|Fabric]], metric views on Databricks).

## Design rules

- Model for the question, not the pipeline: a gold table's shape belongs to
  its consumers.
- Every gold table names an owner and a freshness expectation; a dashboard
  reading stale gold silently is worse than one that errors.
- Access control is strictest here - row filters and column masks from the
  [[DATA-GOVERNANCE-CATALOGS|catalog]] apply where the audience is widest.
- Rebuildable, always: gold is a projection of silver, never the only copy
  of anything.
