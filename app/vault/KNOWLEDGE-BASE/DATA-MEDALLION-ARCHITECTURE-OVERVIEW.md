---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - lakehouse
  - medallion
---

# Medallion Lakehouse Architecture

The medallion architecture organizes a lakehouse into three quality tiers -
[[DATA-BRONZE-LAYER|bronze]], [[DATA-SILVER-LAYER|silver]], and
[[DATA-GOLD-LAYER|gold]] - where each hop adds structure, trust, and business
meaning. Data lands raw, gets cleaned and conformed, and finally gets shaped
for consumption. The names are a convention, not a product feature: the same
pattern runs on [[DATA-LAKEHOUSE-PLATFORMS|Databricks or Microsoft Fabric]]
and on plain open-source parts.

## Why tiers at all

- **Reprocessability.** Bronze keeps the raw truth, so any downstream bug can
  be fixed by replaying transformations rather than re-extracting from
  sources.
- **One cleaning pass, many consumers.** Silver conforms types, keys, and
  duplicates once; every mart and model downstream inherits it.
- **Blast-radius control.** Consumers touch gold; schema drift and source
  mess stay contained in the lower tiers.

## The flow

Sources arrive through [[DATA-INGESTION-PATTERNS|ingestion]] (batch loads,
CDC streams, file drops) into bronze tables stored in an open format -
usually [[DATA-DELTA-LAKE-FORMAT|Delta Lake]] or Iceberg. Transformation
jobs promote data bronze to silver to gold, with
[[DATA-QUALITY-EXPECTATIONS|quality checks]] gating each promotion.
[[DATA-GOVERNANCE-CATALOGS|Catalogs]] (Unity Catalog, Purview) carry
lineage, permissions, and discovery across all three tiers.

## Rules of thumb

- Land first, transform second - never clean data on the way in.
- Keep tier boundaries as contracts: a silver table's schema is a promise.
- Gold is modeled for the reader (stars, wide tables, features), not for the
  pipeline's convenience.
- Everything idempotent: any layer can be rebuilt from the one below it.
