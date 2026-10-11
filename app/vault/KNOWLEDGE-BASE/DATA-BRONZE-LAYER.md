---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - medallion
  - bronze
---

# Bronze Layer

Bronze is the landing tier of the
[[DATA-MEDALLION-ARCHITECTURE-OVERVIEW|medallion architecture]]: data exactly
as it arrived, plus the metadata needed to trust and replay it. Nothing is
cleaned here on purpose - bronze's whole value is being an honest record.

## What belongs in a bronze table

- The source payload, unmodified (columns as-received, bad values included).
- Load metadata: ingestion timestamp, source system, batch or file id, and
  the [[DATA-INGESTION-PATTERNS|ingestion]] watermark that produced it.
- An append-only history. Updates from CDC land as new rows with operation
  markers, not as in-place edits.

## Practices that pay off

- **Schema-on-read tolerance.** Capture unexpected columns into a rescue or
  variant column instead of failing the load; let
  [[DATA-SILVER-LAYER|silver]] decide what to do with them.
- **Partition by arrival, not by meaning.** Ingestion date partitions keep
  loads cheap; business-meaningful layout belongs to silver and gold.
- **Retention is a policy, not an accident.** Keep bronze as long as replays
  and audits need it, and write that number down.

## What bronze is not

Not a queryable product for analysts, not a place for business logic, and
not a dumping ground without contracts -
[[DATA-QUALITY-EXPECTATIONS|expectations]] still run here, just in observe
mode (count the violations, do not block the landing).
