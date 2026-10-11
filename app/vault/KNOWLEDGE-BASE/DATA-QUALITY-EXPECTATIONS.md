---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - data-quality
---

# Data Quality Expectations

Quality checks in a
[[DATA-MEDALLION-ARCHITECTURE-OVERVIEW|medallion lakehouse]] are declared
expectations attached to tables and promotions, not ad hoc assertions
buried in job code. The two platform dialects - Lakeflow/DLT expectations
on Databricks, dataflow and pipeline validations on
[[DATA-LAKEHOUSE-PLATFORMS|Fabric]] - express the same three-mode idea.

## The three modes

- **Observe** (warn): count violations, keep the rows. Right for
  [[DATA-BRONZE-LAYER|bronze]], where the mandate is to record what
  arrived.
- **Drop or quarantine**: violating rows divert to a quarantine table for
  triage. The workhorse mode at the [[DATA-SILVER-LAYER|silver]] gate.
- **Fail**: the batch aborts. Reserved for invariants where partial data
  is worse than no data - key uniqueness, grain integrity, financial
  totals into [[DATA-GOLD-LAYER|gold]].

## What to check where

Structural checks (types, nullability, referential keys) belong at the
silver promotion; distribution checks (volume deltas, freshness, category
drift) run as monitors on top; business-rule checks (a total reconciles
to the source system) gate gold. Reconciliation against the source of
truth is the one check that catches missing-yet-green pipelines - row
counts and control totals per [[DATA-INGESTION-PATTERNS|ingestion]] batch.

## Habits

- Every expectation has an owner and an action; a warning nobody reads is
  decoration.
- Quarantine tables get emptied by process, not by growing forever.
- Thresholds are versioned with the pipeline so a loosened check is a
  visible decision.
