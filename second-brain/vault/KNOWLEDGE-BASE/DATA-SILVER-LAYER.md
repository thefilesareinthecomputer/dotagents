---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - medallion
  - silver
---

# Silver Layer

Silver is where data becomes trustworthy. It reads from
[[DATA-BRONZE-LAYER|bronze]], applies the cleaning and conforming that every
consumer would otherwise repeat, and publishes tables whose schemas are
contracts. Most of a platform's engineering effort lives here.

## The standard moves

- **Type and shape conformance.** Strings become dates, codes become keys,
  nested payloads get flattened to the grain the domain actually uses.
- **Deduplication and merge.** CDC streams collapse to current-state rows
  via MERGE on business keys; late arrivals reconcile against watermarks
  from [[DATA-INGESTION-PATTERNS|ingestion]].
- **Conformed entities.** One customer table, one product table - shared
  keys that every downstream [[DATA-GOLD-LAYER|gold]] model joins against.
- **Quality gates.** [[DATA-QUALITY-EXPECTATIONS|Expectations]] run in
  enforce mode here: rows that break the contract quarantine rather than
  flow through.

## Grain discipline

Every silver table declares its grain (one row per what?) and keeps it.
Grain drift - the same table quietly meaning different things over time -
is the classic silent corruption, and the reason silver schemas change by
migration, not by accident. The [[DATA-DELTA-LAKE-FORMAT|table format]]'s
schema enforcement is the mechanical backstop.

## Relationship to governance

Silver is where [[DATA-GOVERNANCE-CATALOGS|catalog]] lineage starts paying
off: when a gold number looks wrong, the trace back through silver to the
bronze batch that fed it is the debugging path.
