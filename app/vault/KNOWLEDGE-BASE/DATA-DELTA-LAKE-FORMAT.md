---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - lakehouse
  - table-format
---

# Delta Lake and the Open Table Formats

The lakehouse trick is files-plus-transaction-log: Parquet data files with a
log that gives ACID commits, time travel, and schema enforcement on cheap
object storage. Delta Lake is the format under both
[[DATA-LAKEHOUSE-PLATFORMS|Databricks and Microsoft Fabric]]; Apache Iceberg
is the sibling standard, and the two have been converging (UniForm and
interop catalogs read one as the other).

## What the log buys you

- **ACID commits** - a promotion job from [[DATA-BRONZE-LAYER|bronze]] to
  [[DATA-SILVER-LAYER|silver]] either lands whole or not at all.
- **Time travel** - query a table as of a version or timestamp; the cheap
  rollback when a bad batch slips through.
- **Schema enforcement and evolution** - writes that break the contract
  fail loudly; additive columns arrive by declared evolution.
- **MERGE** - the upsert primitive CDC pipelines are built on.

## Operational habits

- Compact small files (OPTIMIZE / auto-compaction) - streaming
  [[DATA-INGESTION-PATTERNS|ingestion]] produces file spray that quietly
  ruins read performance.
- VACUUM with a retention window that respects your time-travel needs.
- Partition sparingly; modern engines prefer clustering/liquid layouts to
  a thousand tiny date partitions.
- Table properties (expectations, constraints) travel with the table -
  [[DATA-QUALITY-EXPECTATIONS|quality]] is part of the format, not just
  the pipeline.
